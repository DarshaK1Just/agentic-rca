"""Anti-hallucination guard: every citation in a generated narrative must map to an
event_id that was actually retrieved. If the LLM invents `event 9999`, we catch it.

This is the enforcement half of the "evidence-or-silence" principle — the synthesis
prompt *asks* the model to cite only provided evidence; this *verifies* it did.
"""
from __future__ import annotations

import re

from rca.store.schema import EvidenceRow

_CITE = re.compile(r"event\s+(\d+)", re.IGNORECASE)


def verify_citations(narrative: str, evidence: list[EvidenceRow]) -> tuple[bool, list[int]]:
    """Return (ok, unsupported_ids). ok=True when every cited event_id was retrieved."""
    allowed = {e.event_id for e in evidence}
    cited = {int(m.group(1)) for m in _CITE.finditer(narrative)}
    unsupported = sorted(cited - allowed)
    return (len(unsupported) == 0, unsupported)
