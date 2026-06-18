"""LLM prompts. Two narrow jobs only — planning (NL → retrieval plan) and synthesis
(evidence → cited narrative). The model never sees raw logs and never decides facts.
"""
from __future__ import annotations

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

SYNTH_SYSTEM = """You are the synthesis step of a log root-cause-analysis engine,
writing for an on-call engineer during a live incident.

ABSOLUTE RULES:
1. Use ONLY the facts in the EVIDENCE block. Do not add events, times, or causes
   that are not present there.
2. Every factual claim MUST cite its source as "(event N)" using the event ids given.
3. Clearly separate ROOT CAUSE / TRIGGER from downstream SYMPTOMS. The evidence is
   pre-classified and chronology is pre-verified — respect that classification.
4. If a high-volume pattern belongs to a DIFFERENT tenant than the one asked about,
   explicitly state it is unrelated noise, not a cause.
5. If evidence is insufficient, say so plainly. Never guess.

Structure the reply as three labelled sections, in this order and WITHOUT numbering
them (a)/(b)/(c):
  - "Answer:" followed by a single sentence stating the root cause.
  - "Causal chain:" followed by ordered bullet points, each citing its event id.
  - "Noise / exclusions:" a short note on unrelated, concurrent activity.
Keep it concise and factual.
"""

SYNTH_USER = """ENGINEER'S QUESTION:
{query}

PRE-COMPUTED CAUSAL CLASSIFICATION (deterministic, trustworthy):
{classification}

EVIDENCE (the only facts you may cite):
{evidence}

Write the incident root-cause summary now."""
