"""Render a CausalChain into (a) a structured result and (b) a human narrative.

Narrative generation has two paths:
  • LLM path   — Gemini/OpenRouter/Ollama writes the prose, constrained by the
                 synthesis prompt and then verified by lineage.verify_citations.
  • Deterministic path — if no LLM is configured (or it emits an unsupported
                 citation), we render a faithful templated summary from the chain.
Either way the FACTS come from the deterministic chain, so output is never
hallucinated; the LLM only improves readability.
"""

import re
from dataclasses import dataclass, field

from rca.agent.prompts import SYNTH_SYSTEM, SYNTH_USER
from rca.store.schema import EvidenceRow
from rca.synth.causal import CausalChain
from rca.synth.lineage import verify_citations

# Standard remediation guidance per failure class. Used to seed the LLM synthesis
# prompt and to enrich the deterministic narrative. These are operational best
# practices — never presented as facts pulled from the logs.
REMEDIATION = {
    "DB_CONN": "Increase / tune the connection-pool size and acquisition timeout; hunt for "
               "connection leaks (unclosed sessions); confirm the database is reachable and "
               "not at max_connections; wrap the datasource in retry-with-backoff + a circuit breaker.",
    "OOM": "Capture a heap dump and inspect dominant retained objects; raise the heap limit only "
           "as a stopgap; look for unbounded caches or collections; tune GC; add memory-pressure alerts.",
    "DEADLOCK": "Identify the conflicting transactions and enforce a consistent lock-acquisition "
                "order; shorten transaction scope; add deadlock-retry; review the isolation level.",
    "THREAD_POOL": "Raise the executor pool / queue capacity as a stopgap; find the slow downstream "
                   "call saturating threads; add timeouts and bulkheads; shed or rate-limit load.",
    "DISK": "Free or expand the affected volume immediately; rotate and compress logs; add "
            "disk-usage alerting; move large artefacts off the hot path.",
    "KAFKA_LAG": "Scale up consumers / partitions; find the stuck or slow consumer; verify broker "
                 "health; raise fetch throughput; alert on consumer-group lag.",
    "GRPC": "Check the downstream service's health and deadlines; add retries with backoff and a "
            "circuit breaker; raise the deadline only if the callee is healthy but slow.",
    "REDIS": "Verify Redis connectivity and the maxmemory/eviction policy; check persistence; add a "
             "connection pool and failover; degrade gracefully on cache miss.",
    "TLS": "Renew the expired certificate / update the trust store; automate certificate rotation; "
           "add expiry monitoring well ahead of time.",
    "TIMEOUT": "Identify the slow dependency; set sensible timeouts with retry + backoff; add a "
               "circuit breaker; investigate latency at the callee.",
    "CIRCUIT": "Find the failing downstream that opened the breaker and restore it; tune breaker "
               "thresholds; ensure graceful degradation while the breaker is open.",
    "UNKNOWN": "Triage from the trigger event and its stack trace; reproduce in a lower environment; "
               "add targeted logging/metrics around the failing component; roll back the most recent "
               "related change if the timing correlates.",
}


def _remediation_for(chain: CausalChain) -> str:
    return REMEDIATION.get(getattr(chain, "trigger_class", "UNKNOWN") or "UNKNOWN",
                           REMEDIATION["UNKNOWN"])


def _extract_answer(text: str, fallback: str) -> str:
    """Pull the one-sentence root cause out of the LLM markdown (the **Answer** line)."""
    for line in text.splitlines():
        m = re.match(r"^\**\s*answer\s*\**\s*[—:\-]*\s*(.+)$", line.strip(), re.IGNORECASE)
        if m and m.group(1).strip():
            return m.group(1).strip().strip("*").strip()
    for line in text.splitlines():       # fallback: first meaningful line
        s = line.strip().lstrip("#* ").strip()
        if s:
            return s
    return fallback


@dataclass
class RCAResult:
    query: str
    tenant_id: str
    answer: str
    narrative: str
    chain: CausalChain
    evidence: list[EvidenceRow]
    llm_used: bool = False
    citations_verified: bool = True
    warnings: list[str] = field(default_factory=list)


def _classification_text(chain: CausalChain) -> str:
    lines = []
    if chain.trigger:
        t = chain.trigger
        lines.append(f"ROOT TRIGGER (rare, earliest): event {t.event_id} @ {t.ts} "
                     f"[{t.component}] {t.message}")
        if t.stack_trace:
            lines.append(f"    stack_trace: {t.stack_trace}")
    for tr in chain.transitions:
        lines.append(f"STATE TRANSITION: event {tr.event_id} @ {tr.ts} "
                     f"[{tr.component}] {tr.message}")
    for c in chain.contributing:
        lines.append(f"CONTRIBUTING: event {c.event_id} @ {c.ts} "
                     f"[{c.component}] {c.message} (x{c.occurrences})")
    for p in chain.precursors:
        lines.append(f"PRECURSOR (before trigger): x{p['count']} from {p['first_seen']} "
                     f"[{p['component']}] {p['template_text']} (e.g. event {p['example_event_id']})")
    for s in chain.symptoms:
        lines.append(f"SYMPTOM (downstream flood): x{s['count']} from {s['first_seen']} "
                     f"[{s['component']}] {s['template_text']} (e.g. event {s['example_event_id']})")
    for n in chain.notes:
        lines.append(f"NOTE: {n}")
    return "\n".join(lines) if lines else "No anomalies classified."


def _evidence_block(evidence: list[EvidenceRow]) -> str:
    return "\n".join(e.as_context_line() for e in evidence)


def deterministic_narrative(chain: CausalChain) -> tuple[str, str]:
    """Faithful, no-LLM summary. Returns (answer, narrative)."""
    if not chain.trigger and not chain.symptoms:
        base = (chain.notes[0] if chain.notes
                else f"No failures found for {chain.tenant_id} in the analysed window.")
        return base, f"**Answer:** {base}"

    if chain.trigger:
        t = chain.trigger
        answer = (f"Root cause for {chain.tenant_id}: {t.message} "
                  f"({t.component}, event {t.event_id}).")
    else:
        answer = f"Anomalies detected for {chain.tenant_id}; no single rare trigger isolated."

    parts = [f"**Answer:** {answer}", "", "**Causal chain (deterministically ordered):**"]
    for p in chain.precursors:
        parts.append(f"- Precursor (resource pressure): x{p['count']} `{p['template_text']}` "
                     f"beginning {p['first_seen']} (e.g. event {p['example_event_id']})")
    for c in chain.contributing[::-1]:
        parts.append(f"- Contributing: {c.message} (event {c.event_id}, x{c.occurrences})")
    if chain.trigger:
        t = chain.trigger
        fc = getattr(chain, "trigger_class", "")
        conf = getattr(chain, "confidence", 0)
        fc_label = f" [{fc}]" if fc and fc != "UNKNOWN" else ""
        conf_label = f" (confidence {conf}/100)" if conf else ""
        parts.append(f"- **Trigger (root cause){fc_label}:** {t.message} -- `{t.component}` "
                     f"(event {t.event_id} @ {t.ts}){conf_label}")
        if t.stack_trace:
            parts.append(f"    - stack trace: `{t.stack_trace.splitlines()[0]}` ...")
    for tr in chain.transitions:
        parts.append(f"- State change: {tr.message} (event {tr.event_id} @ {tr.ts})")
    for s in chain.symptoms:
        parts.append(f"- Symptom (downstream): x{s['count']} `{s['template_text']}` "
                     f"beginning {s['first_seen']} (e.g. event {s['example_event_id']})")
    for n in chain.notes:
        parts.append(f"- _Note: {n}_")
    if chain.trigger:
        parts.append("")
        parts.append("**Recommended actions:**")
        parts.append(f"- {_remediation_for(chain)}")
    return answer, "\n".join(parts)


def synthesize(
    query: str, chain: CausalChain, evidence: list[EvidenceRow], chat_model=None,
) -> RCAResult:
    det_answer, det_narrative = deterministic_narrative(chain)
    result = RCAResult(
        query=query, tenant_id=chain.tenant_id, answer=det_answer,
        narrative=det_narrative, chain=chain, evidence=evidence, llm_used=False,
    )
    # No model, or nothing to ground a narrative on → keep the deterministic answer
    # (also avoids spending an LLM call on an empty/"no failures" result).
    if chat_model is None or not evidence:
        return result

    # LLM path — constrained narration over the deterministic classification.
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        msgs = [
            SystemMessage(content=SYNTH_SYSTEM),
            HumanMessage(content=SYNTH_USER.format(
                query=query,
                trigger_class=getattr(chain, "trigger_class", "UNKNOWN") or "UNKNOWN",
                confidence=getattr(chain, "confidence", 0),
                chronology_verified=chain.chronology_verified,
                classification=_classification_text(chain),
                evidence=_evidence_block(evidence),
                remediation_hint=_remediation_for(chain),
            )),
        ]
        text = chat_model.invoke(msgs).content.strip()
        ok, unsupported = verify_citations(text, evidence)
        if ok:
            result.narrative = text
            result.answer = _extract_answer(text, det_answer)
            result.llm_used = True
        else:
            result.citations_verified = False
            result.warnings.append(
                f"LLM cited unsupported event ids {unsupported}; reverted to "
                f"deterministic narrative to prevent hallucination.")
    except Exception as exc:  # network / quota / provider error → safe fallback
        result.warnings.append(f"LLM synthesis unavailable ({type(exc).__name__}); "
                               f"used deterministic narrative.")
    return result
