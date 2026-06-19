"""Structural + rarity planes, backed by DuckDB (embedded columnar OLAP).

DuckDB gives us SQL over the parsed events with zero server to run. Every agent
retrieval tool ultimately bottoms out in a parameterised query here, so tenant
isolation, temporal windows, level/component filters, and template-frequency
aggregation are all *deterministic and exact* — the LLM never scans raw logs.

Two logical planes live in one table:
  • structural plane — indexed filters on (tenant_id, ts, level, component, template_id)
  • rarity plane     — GROUP BY template_id gives per-tenant inverse-frequency scoring
"""
from __future__ import annotations

import duckdb

from rca.store.schema import EvidenceRow, LogEvent

_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id      BIGINT,
    raw_line_no   BIGINT,
    ts            TIMESTAMP,
    tenant_id     VARCHAR,
    level         VARCHAR,
    severity      INTEGER,
    component     VARCHAR,
    message       VARCHAR,
    template_id   VARCHAR,
    template_text VARCHAR,
    params        JSON,
    stack_trace   VARCHAR,
    source_file   VARCHAR
);
"""


class DuckDBStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.con = duckdb.connect(db_path)
        self.con.execute(_DDL)

    # ── ingestion ──────────────────────────────────────────────────────────
    def load_events(self, events: list[LogEvent]) -> int:
        """Bulk-insert via pandas DataFrame — DuckDB scans it with zero serialization
        overhead, ~10-20× faster than executemany row-by-row."""
        if not events:
            return 0
        import pandas as pd
        df = pd.DataFrame([
            {
                "event_id": e.event_id,
                "raw_line_no": e.raw_line_no,
                "ts": e.ts or None,
                "tenant_id": e.tenant_id,
                "level": e.level.value,
                "severity": e.level.severity,
                "component": e.component,
                "message": e.message,
                "template_id": e.template_id,
                "template_text": e.template_text,
                "params": _json(e.params),
                "stack_trace": e.stack_trace,
                "source_file": e.source_file,
            }
            for e in events
        ])
        self.con.execute("INSERT INTO events SELECT * FROM df")
        return len(df)

    def build_indexes(self) -> None:
        """Create structural indexes once — call AFTER all files are loaded,
        not after each individual file (avoids redundant multi-file rebuilds)."""
        for col in ("tenant_id", "ts", "level", "template_id", "component"):
            self.con.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON events({col})")

    # ── structural plane ─────────────────────────────────────────────────────
    def tenants(self) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT DISTINCT tenant_id FROM events ORDER BY 1").fetchall()]

    def time_bounds(self, tenant_id: str | None = None) -> tuple[str, str]:
        where, params = _tenant_clause(tenant_id)
        r = self.con.execute(
            f"SELECT min(ts), max(ts) FROM events {where}", params).fetchone()
        return (str(r[0]), str(r[1]))

    def query_events(
        self,
        tenant_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
        min_level: str | None = None,
        component_like: str | None = None,
        exclude_template_ids: list[str] | None = None,
        limit: int = 50,
    ) -> list[EvidenceRow]:
        clauses, params = [], []
        if tenant_id:
            clauses.append("tenant_id = ?"); params.append(tenant_id)
        if start:
            clauses.append("ts >= ?"); params.append(start)
        if end:
            clauses.append("ts <= ?"); params.append(end)
        if min_level:
            from rca.store.schema import Level
            clauses.append("severity >= ?"); params.append(Level(min_level).severity)
        if component_like:
            clauses.append("component ILIKE ?"); params.append(f"%{component_like}%")
        if exclude_template_ids:
            placeholders = ",".join("?" * len(exclude_template_ids))
            clauses.append(f"template_id NOT IN ({placeholders})")
            params.extend(exclude_template_ids)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (f"SELECT event_id, raw_line_no, ts, tenant_id, level, component, "
               f"message, template_id, template_text, stack_trace, source_file "
               f"FROM events {where} ORDER BY ts ASC LIMIT {int(limit)}")
        return [_to_evidence(r) for r in self.con.execute(sql, params).fetchall()]

    # ── rarity plane ─────────────────────────────────────────────────────────
    def template_frequencies(
        self, tenant_id: str | None = None,
        start: str | None = None, end: str | None = None,
    ) -> list[dict]:
        """Per-template counts in scope, ascending by frequency (rarest first)."""
        clauses, params = [], []
        if tenant_id:
            clauses.append("tenant_id = ?"); params.append(tenant_id)
        if start:
            clauses.append("ts >= ?"); params.append(start)
        if end:
            clauses.append("ts <= ?"); params.append(end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (f"SELECT template_id, any_value(template_text) AS tmpl, "
               f"max(severity) AS sev, count(*) AS n, min(ts) AS first_seen, "
               f"max(ts) AS last_seen "
               f"FROM events {where} GROUP BY template_id ORDER BY n ASC")
        cols = ["template_id", "template_text", "severity", "count", "first_seen", "last_seen"]
        return [dict(zip(cols, r)) for r in self.con.execute(sql, params).fetchall()]

    def rare_anomalies(
        self, tenant_id: str | None = None,
        start: str | None = None, end: str | None = None,
        min_level: str = "WARN", k: int = 10,
    ) -> list[EvidenceRow]:
        """The diagnostic heart: rare (low-frequency) WARN+/ERROR templates, one
        representative line each, ordered rarest-and-earliest first. This is what
        surfaces the 1-line ConnectionTimeoutException above the 237-line 503 flood."""
        from rca.store.schema import Level
        sev = Level(min_level).severity
        clauses = ["severity >= ?"]
        params: list = [sev]
        if tenant_id:
            clauses.append("tenant_id = ?"); params.append(tenant_id)
        if start:
            clauses.append("ts >= ?"); params.append(start)
        if end:
            clauses.append("ts <= ?"); params.append(end)
        where = "WHERE " + " AND ".join(clauses)
        # Rank templates by rarity, then pull the earliest representative line of each.
        sql = f"""
        WITH scoped AS (SELECT * FROM events {where}),
        freq AS (SELECT template_id, count(*) n FROM scoped GROUP BY template_id),
        ranked AS (
            SELECT s.*, f.n,
                   row_number() OVER (PARTITION BY s.template_id ORDER BY s.ts ASC) rn
            FROM scoped s JOIN freq f USING (template_id)
        )
        SELECT event_id, raw_line_no, ts, tenant_id, level, component,
               message, template_id, template_text, stack_trace, source_file, n
        FROM ranked WHERE rn = 1 ORDER BY n ASC, ts ASC LIMIT {int(k)}
        """
        return [_to_evidence(r, occ=r[-1]) for r in self.con.execute(sql, params).fetchall()]

    def causal_window(
        self, anchor_event_id: int, before: int = 20, after: int = 5,
        tenant_id: str | None = None,
    ) -> list[EvidenceRow]:
        """Chronologically ordered neighbours around an anchor event, scoped to a
        tenant. Used to walk cause→effect and verify a trigger precedes its symptoms."""
        anchor = self.con.execute(
            "SELECT ts, tenant_id FROM events WHERE event_id = ?", [anchor_event_id]
        ).fetchone()
        if not anchor:
            return []
        anchor_ts, anchor_tenant = anchor
        tenant = tenant_id or anchor_tenant
        before_rows = self.con.execute(
            "SELECT event_id, raw_line_no, ts, tenant_id, level, component, message, "
            "template_id, template_text, stack_trace, source_file FROM events "
            "WHERE tenant_id = ? AND ts <= ? ORDER BY ts DESC LIMIT ?",
            [tenant, anchor_ts, before + 1],
        ).fetchall()
        after_rows = self.con.execute(
            "SELECT event_id, raw_line_no, ts, tenant_id, level, component, message, "
            "template_id, template_text, stack_trace, source_file FROM events "
            "WHERE tenant_id = ? AND ts > ? ORDER BY ts ASC LIMIT ?",
            [tenant, anchor_ts, after],
        ).fetchall()
        rows = list(reversed(before_rows)) + list(after_rows)
        return [_to_evidence(r) for r in rows]

    def get_events(self, event_ids: list[int]) -> list[EvidenceRow]:
        if not event_ids:
            return []
        ph = ",".join("?" * len(event_ids))
        sql = (f"SELECT event_id, raw_line_no, ts, tenant_id, level, component, message, "
               f"template_id, template_text, stack_trace, source_file FROM events "
               f"WHERE event_id IN ({ph}) ORDER BY ts ASC")
        return [_to_evidence(r) for r in self.con.execute(sql, event_ids).fetchall()]


# ── helpers ──────────────────────────────────────────────────────────────────
def _json(d: dict) -> str:
    import json
    return json.dumps(d)


def _tenant_clause(tenant_id: str | None) -> tuple[str, list]:
    return ("WHERE tenant_id = ?", [tenant_id]) if tenant_id else ("", [])


def _to_evidence(r: tuple, occ: int = 1) -> EvidenceRow:
    return EvidenceRow(
        event_id=r[0], raw_line_no=r[1], ts=str(r[2]), tenant_id=r[3], level=r[4],
        component=r[5], message=r[6], template_id=r[7], template_text=r[8],
        occurrences=occ, stack_trace=r[9], source_file=r[10],
    )
