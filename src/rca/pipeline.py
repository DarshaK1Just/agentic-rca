"""One-call wiring of the whole stack: log file(s) → ready-to-query RCAEngine.

Shared by the CLI and the Streamlit UI so both exercise the identical path:
    ingest (deterministic) → load DuckDB → [optional] build vector index → RCAEngine
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from rca.agent.graph import RCAEngine
from rca.agent.tools import RetrievalTools
from rca.ingest.normalize import ingest_file
from rca.store.duckdb_store import DuckDBStore
from rca.store.vector_store import TemplateVectorIndex


@dataclass
class BuildStats:
    files: list[str]
    events: int
    distinct_templates: int
    ingest_seconds: float
    vectors_indexed: int = 0


def build_engine(
    log_paths: list[str], with_vectors: bool = False, db_path: str = ":memory:",
) -> tuple[RCAEngine, BuildStats]:
    t0 = time.time()
    store = DuckDBStore(db_path)
    total = 0
    for p in log_paths:
        events = ingest_file(p)
        total += store.load_events(events)
    # Build indexes ONCE after all files are loaded (not per-file).
    store.build_indexes()
    ingest_seconds = time.time() - t0

    distinct = store.con.execute(
        "SELECT count(DISTINCT template_id) FROM events").fetchone()[0]

    vectors = None
    n_vec = 0
    if with_vectors:
        vectors = TemplateVectorIndex()
        n_vec = vectors.build(store)

    engine = RCAEngine(RetrievalTools(store=store, vectors=vectors))
    stats = BuildStats(
        files=[p.split("\\")[-1].split("/")[-1] for p in log_paths],
        events=total, distinct_templates=distinct,
        ingest_seconds=round(ingest_seconds, 3), vectors_indexed=n_vec,
    )
    return engine, stats
