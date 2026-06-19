# RCA Engine — Agentic Root-Cause Analysis for Multi-Tenant Logs
Live APP: https://agentic-rca-rtaycfsfedaxlcrpvkvv9z.streamlit.app/

Ask an outage question in plain English; get a **cited, causally-ordered root-cause narrative**
mined from high-volume, multi-tenant, interleaved log streams.

> **Design thesis:** deterministic structural reduction (tenant partition → Drain3 template
> mining → rarity ranking → chronological trigger/symptom ordering) collapses a 5,000-line
> haystack to ~10 cited rows _before_ any LLM runs. The LLM only plans retrieval and narrates
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

### Local (Development)

```bash
streamlit run app
```

Or with the full path:

```bash
streamlit run src/rca/webapp.py
```

Shows the metrics, the deterministically-classified causal chain (timeline table), the
narrative, and every piece of verbatim, line-addressable evidence.

### Streamlit Cloud (Production Deployment)

Deploy your RCA Engine to the world in 5 minutes:

#### Step 1: Prepare Your Repository

Ensure these files exist in your root directory (they're already created for you):

- `app.py` ✓ — Entry point for Streamlit
- `requirements.txt` ✓ — Python dependencies
- `packages.txt` ✓ — System dependencies
- `.streamlit/config.toml` ✓ — Streamlit configuration
- `.env.example` ✓ — Environment template (DO NOT commit real keys)

#### Step 2: Push to GitHub

```bash
git add app.py requirements.txt packages.txt .streamlit/ .env.example
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

#### Step 3: Deploy on Streamlit Cloud

1. **Create Streamlit Cloud account** (if you don't have one):
   - Go to https://streamlit.io/cloud
   - Sign in with GitHub
2. **Deploy your app**:
   - Click "New app"
   - Select your GitHub repo: `rca-engine`
   - Branch: `main`
   - Main file path: `app.py`
   - Click "Deploy"

3. **Streamlit will start the build** — this takes ~3-5 minutes
   - Your app URL will be: `https://rca-engine-<hash>.streamlit.app`

#### Step 4: Configure Secrets (Critical!)

Your `.env` file should NEVER be committed to GitHub. Instead, use Streamlit Cloud's secret management:

1. In your Streamlit Cloud app dashboard, click **Settings** (gear icon)
2. Click **Secrets** in the left menu
3. Copy the contents from `.streamlit/secrets.toml.example` (after filling in your real keys):
   ```toml
   RCA_LLM_PROVIDER = "gemini"
   GOOGLE_API_KEY = "AIzaSy..."
   RCA_GEMINI_MODEL = "gemini-2.5-flash"
   ```
4. Paste into the Streamlit Cloud secrets editor
5. Click "Save"
6. Streamlit will automatically reload your app with the new secrets

**Where to get your Google API key:**

- Go to https://aistudio.google.com/apikey
- Click "Create API key"
- Copy the key (starts with `AIza`)
- Paste into Streamlit Cloud secrets as `GOOGLE_API_KEY`

#### Step 5: Upload Sample Logs

Once your app is live:

1. Open your Streamlit Cloud app URL
2. In the left sidebar, click "Upload logs"
3. Drop your `.log` files (use the sample data from `data/` directory)
4. The engine auto-detects the format and ingests immediately
5. Start investigating!

---

### Environment Variables Quick Reference

| Variable             | Required?                        | Where to Set                | Example                                  |
| -------------------- | -------------------------------- | --------------------------- | ---------------------------------------- |
| `RCA_LLM_PROVIDER`   | No (default: `gemini`)           | `.env` or Streamlit Secrets | `gemini`, `openrouter`, `ollama`         |
| `GOOGLE_API_KEY`     | Optional                         | Streamlit Secrets           | `AIzaSy...`                              |
| `RCA_GEMINI_MODEL`   | No (default: `gemini-2.5-flash`) | `.env` or Streamlit Secrets | `gemini-2.5-flash`                       |
| `OPENROUTER_API_KEY` | Optional                         | Streamlit Secrets           | `sk-or-v1-...`                           |
| `RCA_EMBED_MODEL`    | No                               | `.env`                      | `sentence-transformers/all-MiniLM-L6-v2` |

**Note:** The engine works 100% without any LLM key (deterministic mode). Add a key if you want AI-powered narrative synthesis.

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
