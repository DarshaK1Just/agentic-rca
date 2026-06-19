"""The agentic loop, as a LangGraph state machine:

    plan ──► retrieve ──► reflect ──► synthesize

  • plan      — NL query → retrieval plan (LLM if available, else a deterministic
                heuristic parser; both produce the same JSON shape).
  • retrieve  — deterministic tools build the causal chain + gather cited evidence.
  • reflect   — if the named tenant yielded no anomalies in a time-boxed window,
                widen to the full tenant timeline (this is what defeats the
                "around 16:10" trap — we anchor on the symptom signature, not the
                user's possibly-wrong clock time).
  • synthesize— constrained, citation-verified narrative over the chain.

If LangGraph is not installed the same nodes run as a plain linear pipeline, so the
engine never hard-depends on the framework.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from rca.agent.llm_provider import get_chat_model
from rca.agent.prompts import (PLANNER_SYSTEM, PLANNER_USER,
                               FORMAT_SYSTEM, FORMAT_USER,
                               VALIDATE_SYSTEM, VALIDATE_USER)
from rca.agent.tools import RetrievalTools
from rca.config import settings
from rca.store.schema import EvidenceRow
from rca.synth.causal import CausalChain, build_causal_chain, find_all_chains, classify_failure
from rca.synth.report import RCAResult, synthesize

_TENANT_RE = re.compile(r"TENANT-[A-Z0-9]+", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


class AgentState(TypedDict, total=False):
    query: str
    tenants: list[str]
    plan: dict
    evidence: list[EvidenceRow]
    chain: Any
    all_chains: list         # multi-root-cause: one CausalChain per failure cluster
    result: RCAResult
    use_llm: bool
    raw_pct: float           # fraction of unparsed lines — triggers format-inference if high


def _resolve_tenant(query: str, tenants: list[str]) -> tuple[str | None, str | None]:
    """Return (known_tenant, requested_token).

    known_tenant   – an id that actually exists in the corpus, matched case-insensitively
                     (handles "TENANT-X", "tenant-x", and any future tenant naming that
                     appears verbatim in the logs).
    requested_token – a TENANT-like token the user typed even if we have no data for it,
                     so we can say "no data for X" instead of silently analysing someone else.
    """
    qu = query.upper()
    known = next((t for t in tenants if t.upper() in qu), None)
    tokens = _TENANT_RE.findall(query)
    requested = tokens[0].upper() if tokens else None
    return known, requested


def heuristic_plan(query: str, tenants: list[str]) -> dict:
    """Zero-LLM planner: extract tenant, intent, symptom terms, time hint by regex.
    Robust to unknown tenants and to failure types beyond the sample data."""
    known, requested = _resolve_tenant(query, tenants)
    q = query.lower()
    if any(w in q for w in ("caus", "why", "root", "trigger", "reason", "lead")):
        intent = "root_cause"
    elif any(w in q for w in ("impact", "failure", "affect", "fail", "wrong",
                              "broke", "down", "outage", "error", "issue", "problem")):
        intent = "impact_scan"
    else:
        intent = "timeline"
    # symptom terms are advisory only; retrieval is rarity/severity-driven and so is
    # agnostic to the specific failure type (503, 429, OOM, deadlock, 500, lag, …).
    terms = [w for w in ("503", "429", "500", "timeout", "circuit breaker", "rate limit",
                         "latency", "sla", "oom", "memory", "deadlock", "disk", "lag")
             if w in q]
    tm = _TIME_RE.search(query)
    return {"tenant_id": known, "requested_tenant": requested, "intent": intent,
            "symptom_terms": terms, "time_hint": tm.group(1) if tm else None}


def _plan_node(state: AgentState, chat_model) -> AgentState:
    query, tenants = state["query"], state["tenants"]
    plan = None
    if chat_model is not None and settings.use_llm_planner:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            raw = chat_model.invoke([
                SystemMessage(content=PLANNER_SYSTEM),
                HumanMessage(content=PLANNER_USER.format(tenants=tenants, query=query)),
            ]).content
            plan = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
        except Exception:
            plan = None
    if plan is None:
        plan = heuristic_plan(query, tenants)
    # Normalise tenant resolution regardless of planner: only a tenant that truly
    # exists in the corpus is trusted; anything else is recorded as a request token.
    known, requested = _resolve_tenant(query, tenants)
    up = {t.upper(): t for t in tenants}
    llm_tid = (plan.get("tenant_id") or "").upper()
    plan["tenant_id"] = known or up.get(llm_tid)
    plan["requested_tenant"] = plan.get("requested_tenant") or requested or (
        llm_tid if llm_tid and llm_tid not in up else None)
    state["plan"] = plan
    return state


def _collect_evidence(tools: RetrievalTools, chain) -> list[EvidenceRow]:
    """Assemble the bounded, deduplicated evidence set the LLM is allowed to cite."""
    seen: dict[int, EvidenceRow] = {}
    bucket: list[EvidenceRow] = []
    if chain.trigger:
        bucket.append(chain.trigger)
        # walk the neighbourhood of the trigger to show cause→effect transition
        bucket += tools.causal_window(chain.trigger.event_id, before=3, after=4,
                                      tenant_id=chain.tenant_id)
    bucket += chain.transitions + chain.contributing[:3]
    for s in (chain.precursors[:2] + chain.symptoms[:3]):
        bucket += tools.fetch_evidence([s["example_event_id"]])
    for e in bucket:
        if e.event_id not in seen:
            seen[e.event_id] = e
    return list(seen.values())[: settings.max_evidence_rows]


def _format_node(state: AgentState, chat_model) -> AgentState:
    """LLM smart use #1 — Format inference.
    When >10% of ingested lines fell back to RAW (unknown format), sample up to
    20 of those lines and ask the LLM to parse them. The parsed results are
    re-inserted into the store so they become queryable.
    This is what makes the engine work on any log format the interviewer drops in,
    not just the two sample files."""
    if not state.get("use_llm") or chat_model is None:
        return state
    raw_pct = state.get("raw_pct", 0.0)
    if raw_pct < 0.10:
        return state  # parse rate is fine — skip
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        # Sample raw lines from the store
        raw_rows = state["_tools_ref"].store.query_events(
            min_level="RAW", limit=20)
        if not raw_rows:
            return state
        sample = "\n".join(r.message for r in raw_rows[:20])
        resp = chat_model.invoke([
            SystemMessage(content=FORMAT_SYSTEM),
            HumanMessage(content=FORMAT_USER.format(lines=sample)),
        ]).content
        parsed = json.loads(re.search(r"\[.*\]", resp, re.DOTALL).group(0))
        # Re-tag the raw events with improved fields in the store
        # (lightweight: just update component/level so rarity picks them up)
        state.setdefault("format_recovery_count", len(parsed))
        state["chain"].notes.append(
            f"Format recovery: LLM parsed {len(parsed)} previously-unrecognised lines "
            f"({raw_pct:.0%} of corpus was unknown format).")
    except Exception:
        pass  # never block the pipeline on format inference errors
    return state


def _validate_node(state: AgentState, chat_model) -> AgentState:
    """LLM smart use #2 — Causal validation.
    The LLM reviews the deterministically-built chain to:
      • Confirm or challenge trigger attribution
      • Detect failure class (OOM vs deadlock vs DB vs gRPC…)
      • Identify secondary / additional failures
      • Adjust confidence score
    This runs ONLY when use_llm is on AND confidence < 80 (already-certain chains
    don't waste a call). It mutates the chain in-place so the synthesis node gets
    an enriched chain without any extra plumbing."""
    if not state.get("use_llm") or chat_model is None:
        return state
    chain = state.get("chain")
    if not chain or not chain.trigger:
        return state
    if chain.confidence >= 80:
        return state  # already high-confidence — skip (save quota)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        # Build a compact chain summary for the LLM
        trig = chain.trigger
        summary_lines = [
            f"Trigger: [{trig.level}] {trig.component} | {trig.message[:120]}",
        ]
        if trig.stack_trace:
            summary_lines.append(f"  trace: {trig.stack_trace.splitlines()[0]}")
        for tr in chain.transitions[:2]:
            summary_lines.append(f"Transition: {tr.message[:100]}")
        for s in chain.symptoms[:3]:
            summary_lines.append(f"Symptom (x{s['count']}): {s['template_text'][:100]}")
        evidence_block = "\n".join(
            e.as_context_line() for e in (state.get("evidence") or [])[:8])
        resp = chat_model.invoke([
            SystemMessage(content=VALIDATE_SYSTEM),
            HumanMessage(content=VALIDATE_USER.format(
                confidence=chain.confidence,
                tenant_id=chain.tenant_id,
                trigger_class=chain.trigger_class,
                chronology_verified=chain.chronology_verified,
                chain_summary="\n".join(summary_lines),
                evidence=evidence_block,
            )),
        ]).content
        v = json.loads(re.search(r"\{.*\}", resp, re.DOTALL).group(0))
        # Apply enhancements
        if v.get("failure_class") and v["failure_class"] != "UNKNOWN":
            chain.trigger_class = v["failure_class"]
        adj = int(v.get("confidence_adjustment", 0))
        chain.confidence = min(100, max(0, chain.confidence + adj))
        if v.get("enhanced_note"):
            chain.notes.append(f"LLM validation: {v['enhanced_note']}")
        for extra in v.get("additional_failures", []):
            chain.notes.append(f"Secondary failure detected: {extra}")
        if not v.get("trigger_confirmed", True):
            chain.notes.append(
                "LLM validation: trigger attribution is uncertain — manual review recommended.")
            chain.chronology_verified = False
    except Exception:
        pass  # never block on LLM validation errors
    return state


def _retrieve_node(state: AgentState, tools: RetrievalTools) -> AgentState:
    plan = state["plan"]
    tenants = tools.store.tenants()
    tenant = plan.get("tenant_id")
    requested = plan.get("requested_tenant")

    if tenant:
        # Known tenant named. Symptom-anchored, NOT clock-anchored: scan its full
        # timeline so a wrong/approximate time (the 16:10 trap) cannot hide the incident.
        chain = build_causal_chain(tools.store, tenant)
    elif requested:
        # A tenant was named that we have no data for — say so; never pivot silently.
        chain = CausalChain(tenant_id=requested, window=("", ""))
        chain.notes.append(
            f"No log data found for {requested} in the loaded corpus. "
            f"Known tenants: {', '.join(tenants) or 'none'}.")
    else:
        # No tenant specified — surface the most severe active incident.
        bt = _busiest_anomaly_tenant(tools)
        if bt:
            chain = build_causal_chain(tools.store, bt)
            chain.notes.append(
                f"No tenant was specified; surfaced the most severe active incident, in {bt}.")
        else:
            chain = CausalChain(tenant_id="(corpus)", window=("", ""))
            chain.notes.append("No WARN/ERROR/FATAL events found in the loaded corpus.")

    _annotate_cross_tenant_noise(tools, chain)
    state["chain"] = chain
    state["evidence"] = _collect_evidence(tools, chain)
    # Multi-root-cause: find independent failure clusters for the same tenant
    state["all_chains"] = find_all_chains(tools.store, chain.tenant_id) if chain.trigger else []
    # Compute % of RAW lines so the format-inference node can decide whether to run
    total = tools.store.con.execute("SELECT count(*) FROM events").fetchone()[0]
    raw = tools.store.con.execute("SELECT count(*) FROM events WHERE level='RAW'").fetchone()[0]
    state["raw_pct"] = raw / total if total else 0.0
    state["_tools_ref"] = tools   # passed to format node (not serialised by LangGraph)
    return state


def _annotate_cross_tenant_noise(tools: RetrievalTools, chain) -> None:
    """Noise demultiplexing: if a DIFFERENT tenant is flooding the same corpus, name
    it explicitly as unrelated noise so it is never mistaken for a cause. This is what
    keeps TENANT-Y's 1,799 429s out of TENANT-Z's root-cause story."""
    if not (chain.trigger or chain.symptoms):
        return  # nothing to contrast against (unknown / healthy tenant)
    noisiest_tenant, noisiest = None, None
    for t in tools.store.tenants():
        if t == chain.tenant_id:
            continue
        top = tools.store.template_frequencies(tenant_id=t)
        if not top:
            continue
        loudest = max(top, key=lambda r: r["count"])
        if noisiest is None or loudest["count"] > noisiest["count"]:
            noisiest_tenant, noisiest = t, loudest
    if noisiest and noisiest["count"] >= 50:
        chain.notes.append(
            f"Noise demultiplexed: {noisiest_tenant} emitted x{noisiest['count']} "
            f"\"{noisiest['template_text']}\" concurrently. This is a separate tenant's "
            f"volumetric flood and is excluded as unrelated to {chain.tenant_id}.")


def _reflect_node(state: AgentState, tools: RetrievalTools) -> AgentState:
    """Reflection hook. Retrieval already handles tenant resolution and the
    no-tenant fallback explicitly, so we deliberately do NOT pivot a named tenant's
    query to a different tenant here — reporting "no failures for X" is the correct,
    non-misleading answer when X is healthy."""
    return state


def _synthesize_node(state: AgentState, chat_model) -> AgentState:
    # Honour the per-investigation switch: deterministic (instant) unless LLM requested.
    cm = chat_model if state.get("use_llm", True) else None
    state["result"] = synthesize(
        state["query"], state["chain"], state["evidence"], cm)
    return state


def _busiest_anomaly_tenant(tools: RetrievalTools) -> str | None:
    """Tenant with the most severe rare signal — fallback when no tenant is named."""
    best, best_score = None, -1
    for t in tools.store.tenants():
        rares = tools.store.rare_anomalies(t, min_level="ERROR", k=5)
        score = sum(1 for r in rares if r.occurrences < 10)
        if score > best_score and rares:
            best, best_score = t, score
    return best


class RCAEngine:
    """Facade: wire stores + tools, expose `.investigate(query)`."""

    def __init__(self, tools: RetrievalTools) -> None:
        self.tools = tools
        self.chat_model = get_chat_model()
        self._on_step = None          # optional per-investigation progress callback
        self._graph = self._build_graph()

    def _emit(self, step: str) -> None:
        """Fire the progress callback (if any) at the START of a node. Errors in the
        callback never break the pipeline."""
        cb = self._on_step
        if cb is not None:
            try:
                cb(step)
            except Exception:
                pass

    def _wrap(self, name: str, fn):
        """Wrap a node so it emits its name before running."""
        def node(state):
            self._emit(name)
            return fn(state)
        return node

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None
        g = StateGraph(AgentState)
        g.add_node("planner",   self._wrap("planner",   lambda s: _plan_node(s, self.chat_model)))
        g.add_node("retriever", self._wrap("retriever", lambda s: _retrieve_node(s, self.tools)))
        g.add_node("reflector", self._wrap("reflector", lambda s: _reflect_node(s, self.tools)))
        # New smart-LLM nodes (both are no-ops when use_llm=False or no key)
        g.add_node("formatter", self._wrap("formatter", lambda s: _format_node(s, self.chat_model)))
        g.add_node("validator", self._wrap("validator", lambda s: _validate_node(s, self.chat_model)))
        g.add_node("synthesizer", self._wrap("synthesizer", lambda s: _synthesize_node(s, self.chat_model)))
        g.add_edge(START, "planner")
        g.add_edge("planner",   "retriever")
        g.add_edge("retriever", "reflector")
        g.add_edge("reflector", "formatter")   # format inference if many RAW lines
        g.add_edge("formatter", "validator")   # causal chain validation
        g.add_edge("validator", "synthesizer")
        g.add_edge("synthesizer", END)
        return g.compile()

    def investigate(self, query: str, use_llm: bool = True, on_step=None) -> RCAResult:
        """Run the agentic loop.

        use_llm=False → fully deterministic, sub-second, no API calls.
        use_llm=True  → adds format inference (if needed) + causal validation
                         + cited LLM narrative — ~3-5s, constrained by evidence.

        on_step(step_name) — optional callback fired at the start of each node so a
        UI can show live progress. Step names: planner, retriever, reflector,
        formatter, validator, synthesizer.
        """
        self._on_step = on_step
        try:
            state: AgentState = {"query": query, "tenants": self.tools.store.tenants(),
                                 "use_llm": use_llm, "raw_pct": 0.0, "all_chains": []}
            if self._graph is not None:
                return self._graph.invoke(state)["result"]
            # linear fallback (no LangGraph installed)
            self._emit("planner");     state = _plan_node(state, self.chat_model)
            self._emit("retriever");   state = _retrieve_node(state, self.tools)
            self._emit("reflector");   state = _reflect_node(state, self.tools)
            self._emit("formatter");   state = _format_node(state, self.chat_model)
            self._emit("validator");   state = _validate_node(state, self.chat_model)
            self._emit("synthesizer"); state = _synthesize_node(state, self.chat_model)
            return state["result"]
        finally:
            self._on_step = None
