"""Stage D1 — streaming line reader with multi-line stack-trace coalescing.

A log "record" is not always a single physical line. A Java stack trace emits a
header line (`... ConnectionTimeoutException ...`) followed by indented
`    at com.x.Y(File.java:NN)` continuation lines. Treating those continuations as
their own events would (a) pollute the template miner and (b) sever the trace from
the error that owns it. So we coalesce: a continuation line is attached to the most
recent record that started with a timestamp.

We yield (line_no, header_text, stack_trace) tuples and never load the whole file
into memory — this is an O(n) single streaming pass, the foundation of the
"deterministic-first" cost story.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

# A new logical record starts with an ISO-8601 timestamp OR a JSON object at column 0.
_RECORD_START = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}|^\{.*\"message\"")


@dataclass
class RawRecord:
    line_no: int                       # 1-based line number of the header
    header: str                        # the timestamped line
    stack_trace_lines: list[str] = field(default_factory=list)

    @property
    def stack_trace(self) -> str | None:
        return "\n".join(self.stack_trace_lines) if self.stack_trace_lines else None


def read_records(path: str) -> Iterator[RawRecord]:
    """Yield one RawRecord per logical event, coalescing continuation lines."""
    current: RawRecord | None = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for idx, raw in enumerate(fh, start=1):
            line = raw.rstrip("\n")
            if _RECORD_START.match(line):
                if current is not None:
                    yield current
                current = RawRecord(line_no=idx, header=line)
            elif current is not None and line.strip():
                # Indented / non-timestamped, non-empty → continuation of prior record.
                current.stack_trace_lines.append(line.strip())
            # else: blank line with no open record — ignore.
    if current is not None:
        yield current
