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
from rca.agent.prompts import PLANNER_SYSTEM, PLANNER_USER
from rca.agent.tools import RetrievalTools
from rca.config import settings
from rca.store.schema import EvidenceRow
from rca.synth.causal import CausalChain, build_causal_chain
from rca.synth.report import RCAResult, synthesize

_TENANT_RE = re.compile(r"TENANT-[A-Z0-9]+", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


class AgentState(TypedDict, total=False):
    query: str
    tenants: list[str]
    plan: dict
    evidence: list[EvidenceRow]
    chain: Any
    result: RCAResult


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
    state["result"] = synthesize(
        state["query"], state["chain"], state["evidence"], chat_model)
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
        self._graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except Exception:
            return None
        g = StateGraph(AgentState)
        g.add_node("planner", lambda s: _plan_node(s, self.chat_model))
        g.add_node("retriever", lambda s: _retrieve_node(s, self.tools))
        g.add_node("reflector", lambda s: _reflect_node(s, self.tools))
        g.add_node("synthesizer", lambda s: _synthesize_node(s, self.chat_model))
        g.add_edge(START, "planner")
        g.add_edge("planner", "retriever")
        g.add_edge("retriever", "reflector")
        g.add_edge("reflector", "synthesizer")
        g.add_edge("synthesizer", END)
        return g.compile()

    def investigate(self, query: str) -> RCAResult:
        state: AgentState = {"query": query, "tenants": self.tools.store.tenants()}
        if self._graph is not None:
            return self._graph.invoke(state)["result"]
        # linear fallback (no LangGraph)
        state = _plan_node(state, self.chat_model)
        state = _retrieve_node(state, self.tools)
        state = _reflect_node(state, self.tools)
        state = _synthesize_node(state, self.chat_model)
        return state["result"]
