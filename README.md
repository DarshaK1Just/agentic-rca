# RCA Engine — Agentic Root-Cause Analysis for Multi-Tenant Logs

Ask an outage question in plain English; get a **cited, causally-ordered root-cause narrative**
mined from high-volume, multi-tenant, interleaved log streams.

> **Design thesis:** deterministic structural reduction (tenant partition → Drain3 template
> mining → rarity ranking → chronological trigger/symptom ordering) collapses a 5,000-line
> haystack to ~10 cited rows *before* any LLM runs. The LLM only plans retrieval and narrates
> verified evidence — it never sees raw logs and cannot introduce uncited facts. The engine
> answers both validation scenarios correctly **with no LLM key at all**.

📄 Full write-up: **[DESIGN.md](DESIGN.md)** · 🗺️ Diagrams: **[ARCHITECTURE.md](ARCHITECTURE.md)**

---

## Quick start

```bash
cd rca-engine
python -m venv .venv && .venv\Scripts\activate     # Windows  (or: source .venv/bin/activate)
pip install -r requirements.txt

# (optional) enable LLM narration — the engine works fully without this
copy .env.example .env        # then paste a free Google AI Studio key into GOOGLE_API_KEY
```

> `sentence-transformers` / `chromadb` (the optional semantic layer) pull in `torch`. They are
> only needed for `--vectors`; the two validation scenarios are solved by the deterministic +
> rarity path and need neither.

## Run the two validation scenarios

```bash
# Scenario 1 — chronological trigger extraction
python -m rca.cli investigate data/production_incident_01.log \
  -q "What caused the 503 errors for TENANT-X around 16:10?"

# Scenario 2 — high-volume noise demultiplexing
python -m rca.cli investigate data/auth_rate_limit_noise.log \
  -q "Identify any system failures impacting TENANT-Z during the authentication volume spike."

# Deterministic corpus profile (tenants, templates, rare anomalies)
python -m rca.cli profile data/production_incident_01.log
```

Set `PYTHONPATH=src` if you run without `pip install -e .`.

## Web UI

```bash
streamlit run src/rca/webapp.py
```
Shows the metrics, the deterministically-classified causal chain (timeline table), the
narrative, and every piece of verbatim, line-addressable evidence.

## What you get (Scenario 1, abridged)
```
Root cause for TENANT-X: pool.ConnectionTimeoutException ... (com.service.db.DataSource, event 3252)
- Precursor: x25 connection pool utilization > 90% (from 12:02:55)
- Trigger:   ConnectionTimeoutException @ 12:02:58.378  [+ stack trace]
- State change: CircuitBreaker CLOSED -> OPEN @ 12:02:58.408
- Symptom:   x237 503 Service Unavailable (from 12:02:58.661)
[causal chronology: VERIFIED] [citations verified: True]
```

## Tests
```bash
pytest -q          # 8 tests; both validation scenarios assert correctness with NO LLM key
```

## Layout
```
src/rca/
  ingest/   reader · parser · drain_miner · normalize     # deterministic pipeline
  store/    schema · duckdb_store · rarity · vector_store  # 3 indexing planes
  agent/    llm_provider · tools · prompts · graph         # LangGraph loop + BYOK
  synth/    causal · report · lineage                      # verifiable chain + anti-hallucination
  cli.py · webapp.py · pipeline.py · config.py
tests/      test_ingest · test_scenarios
data/       the two provided logs
```

## Configuration
All runtime knobs are environment variables (see [.env.example](.env.example)); no key is ever
hardcoded. Swap the model with `RCA_LLM_PROVIDER=gemini|openrouter|ollama`. Dependencies are
pinned in [requirements.txt](requirements.txt).
