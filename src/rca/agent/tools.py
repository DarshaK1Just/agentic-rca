"""Retrieval tools — the only way the agent touches data. Every tool returns
lineage-stamped EvidenceRow objects (or plain dicts), never raw file text. Each is a
thin, deterministic wrapper over the DuckDB/vector planes, so the agent's "actions"
are exact and auditable.

These same functions are callable directly by the deterministic planner (no LLM),
which is what lets the engine run end-to-end with zero API key.
"""
from __future__ import annotations

from dataclasses import dataclass

from rca.store.duckdb_store import DuckDBStore
from rca.store.schema import EvidenceRow
from rca.store.vector_store import TemplateVectorIndex


@dataclass
class RetrievalTools:
    store: DuckDBStore
    vectors: TemplateVectorIndex | None = None

    # structural plane
    def structured_query(self, **kw) -> list[EvidenceRow]:
        return self.store.query_events(**kw)

    def causal_window(self, anchor_event_id: int, before: int = 20, after: int = 5,
                      tenant_id: str | None = None) -> list[EvidenceRow]:
        return self.store.causal_window(anchor_event_id, before, after, tenant_id)

    def fetch_evidence(self, event_ids: list[int]) -> list[EvidenceRow]:
        return self.store.get_events(event_ids)

    # rarity plane
    def rare_templates(self, tenant_id: str | None = None, start: str | None = None,
                       end: str | None = None, min_level: str = "WARN",
                       k: int = 10) -> list[EvidenceRow]:
        return self.store.rare_anomalies(tenant_id, start, end, min_level, k)

    def template_frequencies(self, tenant_id: str | None = None, start: str | None = None,
                             end: str | None = None) -> list[dict]:
        return self.store.template_frequencies(tenant_id, start, end)

    # semantic plane
    def semantic_search(self, query: str, tenant_id: str | None = None,
                        k: int = 8) -> list[dict]:
        if self.vectors is None:
            return []
        return self.vectors.search(query, tenant_id, k)
