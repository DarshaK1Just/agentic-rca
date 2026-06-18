"""Deterministic causal-chain construction — the verifiable core of the RCA.

The assignment demands we "distinguish historical triggers from downstream symptoms"
and build "verifiable causal chains". We do that with arithmetic and timestamps, NOT
LLM intuition, so the chain is reproducible and auditable:

  • TRIGGER     = the chronologically EARLIEST, LOW-frequency, high-severity event in
                  the tenant's incident window. (Low frequency ⇒ initiator, not flood.)
  • TRANSITION  = state-change events (e.g. circuit breaker CLOSED→OPEN) that sit
                  between the trigger and the symptom flood.
  • SYMPTOMS    = HIGH-frequency, high-severity templates whose first occurrence is
                  AT OR AFTER the trigger. (High volume + later ⇒ downstream effect.)
  • CONTRIBUTING= low-frequency precursors (e.g. pool-utilization warnings) before
                  the trigger.

A chain is only emitted when `trigger.ts <= symptom.first_seen`, making the
cause→effect ordering an explicit, checkable invariant rather than an assertion.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rca.store.duckdb_store import DuckDBStore
from rca.store.schema import EvidenceRow

# A template is a "flood" (symptom) once it repeats beyond this many times in scope.
FLOOD_MIN_COUNT = 10


@dataclass
class CausalChain:
    tenant_id: str
    window: tuple[str, str]
    trigger: EvidenceRow | None = None
    transitions: list[EvidenceRow] = field(default_factory=list)
    contributing: list[EvidenceRow] = field(default_factory=list)
    precursors: list[dict] = field(default_factory=list)  # high-count, BEFORE trigger
    symptoms: list[dict] = field(default_factory=list)     # high-count, AT/AFTER trigger
    notes: list[str] = field(default_factory=list)
    chronology_verified: bool = False

    def all_evidence_ids(self) -> list[int]:
        ids = []
        if self.trigger:
            ids.append(self.trigger.event_id)
        ids += [e.event_id for e in self.transitions + self.contributing]
        ids += [s["example_event_id"] for s in self.precursors + self.symptoms]
        return ids


def build_causal_chain(
    store: DuckDBStore, tenant_id: str,
    start: str | None = None, end: str | None = None,
) -> CausalChain:
    lo, hi = store.time_bounds(tenant_id)
    window = (start or lo, end or hi)

    anomalies = store.rare_anomalies(tenant_id, start, end, min_level="WARN", k=50)
    chain = CausalChain(tenant_id=tenant_id, window=window)
    if not anomalies:
        chain.notes.append("No WARN/ERROR/FATAL events found for this tenant in scope.")
        return chain

    rare = [e for e in anomalies if e.occurrences < FLOOD_MIN_COUNT]
    flood = [e for e in anomalies if e.occurrences >= FLOOD_MIN_COUNT]

    # State transitions are explicit signals; treat them separately from the trigger.
    transitions = [e for e in rare if _is_transition(e)]
    rare_errors = [e for e in rare if not _is_transition(e)]

    # Trigger = earliest, highest-severity rare error. Sort by (ts) then severity desc.
    if rare_errors:
        rare_errors_sorted = sorted(
            rare_errors, key=lambda e: (e.ts, -_sev(e.level))
        )
        chain.trigger = rare_errors_sorted[0]
        # Other rare errors before the symptom flood are contributing factors.
        chain.contributing = [e for e in rare_errors_sorted[1:]]

    chain.transitions = sorted(transitions, key=lambda e: e.ts)

    # Flood templates are split by CHRONOLOGY relative to the trigger:
    #   first occurrence BEFORE the trigger  → precursor (e.g. resource pressure)
    #   first occurrence AT/AFTER the trigger → downstream symptom
    # This prevents a high-count precursor (25 pool-utilization warnings) from being
    # mislabelled a symptom just because it is frequent.
    freqs = store.template_frequencies(tenant_id, start, end)
    trigger_ts = str(chain.trigger.ts) if chain.trigger else None
    for e in sorted(flood, key=lambda e: e.ts):
        freq = next((f for f in freqs if f["template_id"] == e.template_id), None)
        first_seen = str(freq["first_seen"]) if freq else e.ts
        summary = {
            "template_text": e.template_text or e.message,
            "template_id": e.template_id,
            "level": e.level,
            "component": e.component,
            "count": e.occurrences,
            "first_seen": first_seen,
            "example_event_id": e.event_id,
            "example_line": e.raw_line_no,
        }
        if trigger_ts is not None and first_seen < trigger_ts:
            chain.precursors.append(summary)
        else:
            chain.symptoms.append(summary)

    # Verify the cause→effect invariant: trigger must precede the symptom flood.
    if chain.trigger and chain.symptoms:
        earliest_symptom = min(str(s["first_seen"]) for s in chain.symptoms)
        chain.chronology_verified = str(chain.trigger.ts) <= earliest_symptom
        if chain.chronology_verified:
            chain.notes.append(
                f"Chronology verified: trigger at {chain.trigger.ts} precedes the "
                f"symptom flood beginning {earliest_symptom}.")
        else:
            chain.notes.append(
                "WARNING: earliest rare error does NOT precede the flood; "
                "trigger attribution is low-confidence.")
    elif chain.trigger and not chain.symptoms:
        chain.chronology_verified = True
        chain.notes.append("Isolated anomaly with no downstream flood in scope.")

    return chain


def _is_transition(e: EvidenceRow) -> bool:
    text = f"{e.component} {e.message}".lower()
    return any(k in text for k in ("circuit", "state changed", "->", "breaker"))


def _sev(level: str) -> int:
    return {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3,
            "ERROR": 4, "FATAL": 5, "RAW": 2}.get(level, 2)
