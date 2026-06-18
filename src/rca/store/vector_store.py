"""Semantic plane — embeddings over the DISTINCT template catalog, not raw lines.

This is the deliberate antidote to context-window pollution. If we embedded all
5,002 raw lines, TENANT-Y's 1,799 near-identical 429 messages would form a dense
cluster that dominates any top-k similarity search. Instead we embed each *template*
exactly once (a few dozen vectors total), tagged with tenant + frequency metadata.
A flood therefore contributes a single vector, and open-ended queries like
"anything about timeouts" surface rare templates on equal footing.

Heavy deps (chromadb, sentence-transformers) are imported lazily so the
deterministic pipeline and its tests never require them.
"""
from __future__ import annotations

from rca.config import settings
from rca.store.duckdb_store import DuckDBStore


class TemplateVectorIndex:
    def __init__(self) -> None:
        self._client = None
        self._collection = None

    def _ensure(self):
        if self._collection is not None:
            return
        import chromadb
        from chromadb.utils import embedding_functions

        self._client = chromadb.Client()  # in-memory; ephemeral per run
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embed_model
        )
        # Fresh collection each run keeps the prototype reproducible.
        try:
            self._client.delete_collection("templates")
        except Exception:
            pass
        self._collection = self._client.create_collection(
            "templates", embedding_function=ef, metadata={"hnsw:space": "cosine"}
        )

    def build(self, store: DuckDBStore) -> int:
        """Index one vector per (tenant, template) pair with frequency metadata."""
        self._ensure()
        ids, docs, metas = [], [], []
        for tenant in store.tenants():
            for row in store.template_frequencies(tenant_id=tenant):
                if not row["template_text"]:
                    continue
                ids.append(f"{tenant}::{row['template_id']}")
                docs.append(row["template_text"])
                metas.append({
                    "tenant_id": tenant,
                    "template_id": row["template_id"],
                    "count": int(row["count"]),
                    "severity": int(row["severity"]),
                })
        if ids:
            self._collection.add(ids=ids, documents=docs, metadatas=metas)
        return len(ids)

    def search(self, query: str, tenant_id: str | None = None, k: int = 8) -> list[dict]:
        self._ensure()
        where = {"tenant_id": tenant_id} if tenant_id else None
        res = self._collection.query(query_texts=[query], n_results=k, where=where)
        out = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({
                "template_text": doc,
                "template_id": meta["template_id"],
                "tenant_id": meta["tenant_id"],
                "count": meta["count"],
                "severity": meta["severity"],
                "distance": round(float(dist), 4),
            })
        return out
