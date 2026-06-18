"""Stage D4 — orchestrate reader → parser → Drain3 into canonical LogEvent records.

This is the public entrypoint of the deterministic pipeline:

    events = ingest_file("data/production_incident_01.log")

A handful of cheap regexes pull the most useful structured params (status code,
DB cluster, duration, client IP) into `params` for precise structural filtering
later. Everything is still single-pass and LLM-free.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator

from rca.ingest.drain_miner import DrainMiner
from rca.ingest.parser import parse_header
from rca.ingest.reader import read_records
from rca.store.schema import Level, LogEvent

_PARAM_PATTERNS = {
    "status": re.compile(r"Status:?\s*(\d{3})"),
    "db_cluster": re.compile(r"cluster\s*\[?([A-Za-z0-9\-]+)\]?", re.IGNORECASE),
    "duration_ms": re.compile(r"(\d+)\s*ms"),
    "client_ip": re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})"),
    "client_id": re.compile(r"client_id:\s*(cl_\d+)"),
}


def _extract_params(message: str) -> dict:
    out: dict = {}
    for key, pat in _PARAM_PATTERNS.items():
        m = pat.search(message)
        if m:
            out[key] = m.group(1)
    return out


def ingest_file(path: str) -> list[LogEvent]:
    """Parse one log file into canonical, template-tagged LogEvent records."""
    return list(iter_events(path))


def iter_events(path: str) -> Iterator[LogEvent]:
    source = os.path.basename(path)
    miner = DrainMiner()
    eid = 0
    for rec in read_records(path):
        parsed = parse_header(rec.header)
        template_id, template_text = miner.mine(parsed["message"])
        eid += 1
        yield LogEvent(
            event_id=eid,
            raw_line_no=rec.line_no,
            ts=parsed["ts"],
            tenant_id=parsed["tenant"],
            level=Level(parsed["level"]),
            component=parsed["component"],
            message=parsed["message"],
            template_id=template_id,
            template_text=template_text,
            params=_extract_params(parsed["message"]),
            stack_trace=rec.stack_trace,
            source_file=source,
        )
