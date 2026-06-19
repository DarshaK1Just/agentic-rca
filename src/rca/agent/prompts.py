"""LLM prompts. Two narrow jobs only — planning (NL → retrieval plan) and synthesis
(evidence → cited narrative). The model never sees raw logs and never decides facts.
"""
from __future__ import annotations

FORMAT_SYSTEM = """You are a log-format expert. You will be shown a sample of log lines
that failed to parse with a standard parser. Identify the format and extract structured
fields from each line.

Return ONLY a JSON array where each element has exactly these keys:
  "ts": ISO-8601 timestamp string or "" if absent
  "tenant": tenant/service identifier or "DEFAULT" if absent
  "level": one of DEBUG INFO WARN ERROR FATAL or "INFO" if absent
  "component": logger/class name or "" if absent
  "message": the log message content

Return exactly as many elements as input lines, in the same order.
If a line is unparseable, use empty strings for all fields except message (use the raw line).
"""

FORMAT_USER = """Parse these log lines:
{lines}
JSON array:"""

VALIDATE_SYSTEM = """You are a causal-chain validator for a log root-cause-analysis engine.
You will receive a deterministically-built causal chain and the raw evidence.
Your job is to:
1. Confirm or challenge the trigger attribution (is the identified trigger truly causal, or is it a symptom?)
2. Identify any additional failure classes or patterns the deterministic layer missed
3. Flag if this looks like gradual degradation rather than a discrete trigger
4. If multiple independent failures exist, name them

Return a JSON object with:
  "trigger_confirmed": true/false
  "failure_class": e.g. "OOM", "DEADLOCK", "DB_CONN", "THREAD_POOL", "DISK", "KAFKA_LAG", "GRPC", "REDIS", "TIMEOUT", "UNKNOWN"
  "confidence_adjustment": integer -20 to +20 (adjust the deterministic score)
  "enhanced_note": one sentence of additional context, or ""
  "additional_failures": list of strings describing any secondary failures found, or []
"""

VALIDATE_USER = """DETERMINISTIC CHAIN (confidence {confidence}/100):
Tenant: {tenant_id}
Trigger class: {trigger_class}
Chronology verified: {chronology_verified}

CHAIN SUMMARY:
{chain_summary}

EVIDENCE (verbatim):
{evidence}

Validate and enhance:"""

PLANNER_SYSTEM = """You are the planning step of a log root-cause-analysis engine.
Translate the engineer's natural-language question into a STRICT JSON retrieval plan.
You do NOT answer the question. You only extract retrieval parameters.

Return ONLY a JSON object with these keys:
  "tenant_id":   the tenant the question is about, e.g. "TENANT-X" (or null if none named)
  "symptom_terms": list of short strings describing the symptom mentioned (e.g. ["503","circuit breaker"]) or []
  "intent":      one of "root_cause" | "impact_scan" | "timeline"
  "time_hint":   any clock time mentioned by the user as "HH:MM" or null

Rules:
- Do NOT invent a tenant that is not in the question.
- If the user gives a time, copy it verbatim into time_hint; the engine decides whether to trust it.
"""

PLANNER_USER = """Available tenants: {tenants}
Question: {query}
JSON plan:"""

SYNTH_SYSTEM = """You are the synthesis step of a log root-cause-analysis engine.
You write for an on-call engineer who must act within two minutes.

ABSOLUTE RULES (facts):
1. For any statement about what the logs show — events, timestamps, components, counts,
   or causes — use ONLY the EVIDENCE and CLASSIFICATION provided. Never invent log facts.
2. Every such factual claim MUST cite its source as "(event N)" using the given event ids.
3. Respect the pre-computed classification: the TRIGGER is the root cause, SYMPTOMS are
   downstream effects, and chronology is already verified. Do not relabel them.
4. If a high-volume pattern belongs to a DIFFERENT tenant than the one asked about,
   explicitly state it is unrelated noise, not a cause.
5. If the evidence is insufficient for a section, say so plainly rather than guessing.

Write GitHub-flavoured markdown with these EXACT bold section headers, in this order
(no numbering, no (a)/(b)/(c) labels):

**Answer** — one crisp sentence naming the root cause and the affected tenant.
**What happened** — 3 to 6 ordered bullets tracing trigger → state change → symptom
   flood. Each bullet cites its event id and explains the failure mechanism concretely.
**Impact** — one or two sentences on the observable effect: what broke and how widespread,
   cited where the evidence supports it.
**Recommended actions** — 2 to 4 concrete, prioritised remediation steps suited to the
   failure class. These are operational guidance, NOT log facts, so they need no citation,
   but they must be standard, sensible practice for THIS failure type. Lead with the
   fastest safe mitigation, then the durable fix.
**Noise / exclusions** — one short note on unrelated concurrent activity (another tenant's
   flood), or "None observed." when there is nothing to exclude.

Be concise, concrete and confident. No preamble before the Answer header.
"""

SYNTH_USER = """ENGINEER'S QUESTION:
{query}

PRE-COMPUTED CAUSAL CLASSIFICATION (deterministic, trustworthy):
Failure class: {trigger_class}
Confidence: {confidence}/100
Chronology verified: {chronology_verified}
{classification}

EVIDENCE (the only facts you may cite):
{evidence}

REMEDIATION THEMES for a {trigger_class} failure (adapt to the specifics above —
do not copy verbatim, and omit any that don't fit):
{remediation_hint}

Write the incident root-cause summary now."""
