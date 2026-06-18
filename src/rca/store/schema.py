"""Canonical event schema — the single source of truth for a parsed log record.

Every downstream component (DuckDB store, vector store, agent tools, report) speaks
in terms of `LogEvent`. The schema is intentionally additive: variable fields live in
the free-form `params` dict so a never-before-seen log shape does not require a
migration — it just lands with fewer params and (if unparseable) level=RAW.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Level(str, Enum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"
    RAW = "RAW"  # fallback for lines that don't match the known grammar

    @property
    def severity(self) -> int:
        order = {
            "TRACE": 0, "DEBUG": 1, "INFO": 2,
            "WARN": 3, "ERROR": 4, "FATAL": 5, "RAW": 2,
        }
        return order[self.value]


class LogEvent(BaseModel):
    """One logical event. Multi-line stack traces are coalesced into `stack_trace`."""

    event_id: int = Field(..., description="Stable, monotonic citation handle")
    raw_line_no: int = Field(..., description="1-based line number in the source file")
    ts: str = Field(..., description="ISO-8601 UTC timestamp (string for lossless storage)")
    tenant_id: str = Field(..., description="Partition key, e.g. TENANT-X")
    level: Level
    component: str = Field("", description="Logger component, e.g. com.service.db.DataSource")
    message: str = ""
    template_id: str = Field("", description="Drain3 cluster id — the dedup key")
    template_text: str = Field("", description="Templated message with <*> wildcards")
    params: dict = Field(default_factory=dict, description="Extracted variables")
    stack_trace: str | None = None
    source_file: str = ""

    def citation(self) -> str:
        return f"{self.source_file}:{self.raw_line_no} (event {self.event_id})"


class EvidenceRow(BaseModel):
    """A retrieved, lineage-stamped row returned to the agent. Mirrors LogEvent but
    is the *only* shape the LLM is allowed to cite from — enforced at synthesis."""

    event_id: int
    raw_line_no: int
    ts: str
    tenant_id: str
    level: str
    component: str
    message: str
    template_id: str
    template_text: str
    occurrences: int = Field(1, description="How many lines share this template in scope")
    stack_trace: str | None = None
    source_file: str = ""

    def citation(self) -> str:
        return f"{self.source_file}:{self.raw_line_no} (event {self.event_id})"

    def as_context_line(self) -> str:
        base = (f"[event {self.event_id} | line {self.raw_line_no} | {self.ts} | "
                f"{self.tenant_id} | {self.level} | {self.component}] {self.message}")
        if self.occurrences > 1:
            base += f"  (×{self.occurrences} occurrences of this template)"
        if self.stack_trace:
            base += f"\n    stack_trace: {self.stack_trace}"
        return base
