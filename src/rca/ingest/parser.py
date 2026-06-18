"""Stage D2 — deterministic field extraction via a single anchored regex.

The provided logs share one grammar:

    <ISO-8601 ts> [TENANT-ID] <LEVEL> [<component>] <message>

>99% of lines match this exactly, so a compiled regex parses the entire corpus in
one pass with zero LLM cost. Anything that does NOT match is not dropped — it is
returned with level=RAW so it still reaches the store and the vector index (the
"never block ingestion on an unknown shape" rule). This is the deterministic floor
the whole latency/cost argument rests on.
"""
from __future__ import annotations

import re

from rca.store.schema import Level

# Groups: ts, tenant, level, component, message
_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s+"
    r"\[(?P<tenant>[^\]]+)\]\s+"
    r"(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+"
    r"\[(?P<component>[^\]]+)\]\s+"
    r"(?P<message>.*)$"
)


class ParsedLine(dict):
    """Thin dict subclass for readable access; keys: ts, tenant, level, component, message."""


def parse_header(header: str) -> ParsedLine:
    """Parse one timestamped header line. Returns a RAW-tagged record if it doesn't match."""
    m = _LINE.match(header)
    if not m:
        return ParsedLine(
            ts="", tenant="UNKNOWN", level=Level.RAW.value,
            component="", message=header.strip(),
        )
    d = m.groupdict()
    return ParsedLine(
        ts=d["ts"],
        tenant=d["tenant"].strip(),
        level=d["level"],
        component=d["component"].strip(),
        message=d["message"].strip(),
    )
