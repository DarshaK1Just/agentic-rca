"""Stage D2 — deterministic field extraction with multi-format support.

The interviewer will introduce logs with:
  • Different timestamp formats (no millis, +00:00 offset, epoch ms)
  • JSON-structured log lines
  • Alternative level names: SEVERE, CRITICAL, WARNING, ERR, FATAL
  • Logs without a tenant field (single-service mode)
  • Node.js / Python traceback continuations
  • syslog-style headers

Strategy:
  1. Try each format in order (fastest / most common first).
  2. Never drop a line — unmatched lines get level=RAW and still flow through
     the pipeline (they are ingested, template-mined and embeddable).
  3. Normalise level aliases so downstream code only sees DEBUG/INFO/WARN/ERROR/FATAL/RAW.
"""
from __future__ import annotations

import json
import re

from rca.store.schema import Level

# ── level normalisation ──────────────────────────────────────────────────────
_LEVEL_MAP = {
    "TRACE": Level.TRACE,  "DEBUG": Level.DEBUG,
    "INFO": Level.INFO,    "INFORMATION": Level.INFO,
    "WARN": Level.WARN,    "WARNING": Level.WARN,
    "ERROR": Level.ERROR,  "ERR": Level.ERROR,   "SEVERE": Level.ERROR,
    "CRITICAL": Level.ERROR,
    "FATAL": Level.FATAL,
}

def _norm_level(raw: str) -> str:
    return _LEVEL_MAP.get(raw.upper(), Level.RAW).value


# ── Format 1: standard (what both sample files use) ─────────────────────────
# 2026-05-26T12:00:00.090Z [TENANT-X] INFO  [com.service.X] message
_STD = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"\[(?P<tenant>[^\]]+)\]\s+"
    r"(?P<level>TRACE|DEBUG|INFO|INFORMATION|WARN(?:ING)?|ERR(?:OR)?|SEVERE|CRITICAL|FATAL)\s+"
    r"\[(?P<component>[^\]]+)\]\s+"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)

# ── Format 2: same but without tenant (single-service log) ───────────────────
# 2026-05-26T12:00:00.090Z INFO  [com.service.X] message
_NO_TENANT = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>TRACE|DEBUG|INFO|INFORMATION|WARN(?:ING)?|ERR(?:OR)?|SEVERE|CRITICAL|FATAL)\s+"
    r"\[(?P<component>[^\]]+)\]\s+"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)

# ── Format 3: JSON log line ──────────────────────────────────────────────────
# {"ts":"...","tenant":"...","level":"...","component":"...","message":"..."}
_JSON_FIELDS = {
    "ts":        ["ts", "timestamp", "time", "@timestamp"],
    "tenant":    ["tenant", "tenant_id", "tenantId", "service", "app"],
    "level":     ["level", "severity", "log_level", "logLevel"],
    "component": ["component", "logger", "class", "source", "module"],
    "message":   ["message", "msg", "body", "text"],
}

def _try_json(line: str) -> dict | None:
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    out: dict = {}
    for key, candidates in _JSON_FIELDS.items():
        for c in candidates:
            if c in obj:
                out[key] = str(obj[c])
                break
        else:
            out[key] = ""
    return out


# ── Format 4: syslog (RFC 3164 / 5424 simplified) ────────────────────────────
# May 26 16:10:00 hostname service[pid]: message
# <34>1 2026-05-26T16:10:00Z hostname service - - - message
_SYSLOG = re.compile(
    r"(?P<ts>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s+"
    r"\S+\s+(?P<component>\S+?)(?:\[\d+\])?:\s+(?P<message>.*)",
)


# ── Format 5: level-prefixed (common in containerised services) ──────────────
# ERROR [2026-05-26 16:10:00] [TENANT-X] com.service.X: message
_LEVEL_FIRST = re.compile(
    r"^(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERR(?:OR)?|SEVERE|CRITICAL|FATAL)\s+"
    r"\[?(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\]]*)\]?\s+"
    r"(?:\[(?P<tenant>[^\]]+)\]\s+)?"
    r"(?P<component>\S+)\s*:\s+"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)


class ParsedLine(dict):
    """Thin dict with keys: ts, tenant, level, component, message."""


def parse_header(header: str) -> ParsedLine:
    """Try each format; fall back to RAW so no line is ever dropped."""
    # Format 1 — standard (fastest match for the sample data)
    m = _STD.match(header)
    if m:
        d = m.groupdict()
        return ParsedLine(ts=d["ts"].strip(), tenant=d["tenant"].strip(),
                          level=_norm_level(d["level"]), component=d["component"].strip(),
                          message=d["message"].strip())

    # Format 2 — no tenant
    m = _NO_TENANT.match(header)
    if m:
        d = m.groupdict()
        return ParsedLine(ts=d["ts"].strip(), tenant="DEFAULT",
                          level=_norm_level(d["level"]), component=d["component"].strip(),
                          message=d["message"].strip())

    # Format 3 — JSON
    j = _try_json(header)
    if j and j.get("message"):
        return ParsedLine(ts=j.get("ts", ""), tenant=j.get("tenant", "DEFAULT") or "DEFAULT",
                          level=_norm_level(j.get("level", "INFO")),
                          component=j.get("component", ""), message=j.get("message", ""))

    # Format 4 — level-first
    m = _LEVEL_FIRST.match(header)
    if m:
        d = m.groupdict()
        return ParsedLine(ts=d["ts"].strip(), tenant=(d["tenant"] or "DEFAULT").strip(),
                          level=_norm_level(d["level"]), component=(d["component"] or "").strip(),
                          message=d["message"].strip())

    # Format 5 — syslog
    m = _SYSLOG.match(header)
    if m:
        d = m.groupdict()
        return ParsedLine(ts=d["ts"].strip(), tenant="DEFAULT", level=Level.INFO.value,
                          component=d["component"].strip(), message=d["message"].strip())

    # RAW fallback — still ingested, still analysable
    return ParsedLine(ts="", tenant="UNKNOWN", level=Level.RAW.value,
                      component="", message=header.strip())
