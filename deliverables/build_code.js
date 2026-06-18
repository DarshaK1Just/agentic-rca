// Prototype Code & How-to-Run guide
const path = require("path");
const L = require("./lib");
const { T, B, code, H1, H2, H3, P, bullet, num, codeBlock, table, titlePage,
        buildDoc, toc, write } = L;

const c = [];
c.push(...titlePage("Prototype Code & How-to-Run Guide",
  "Agentic Root-Cause-Analysis Engine", "COD-RCA-001",
  "How to set up, run and test the reference implementation, with a map of the codebase and "
  + "the end-to-end execution path for each natural-language incident query."));
c.push(...toc());

c.push(H1("1. What the Prototype Does"));
c.push(P([T("A runnable implementation of the RCA engine. It ingests the supplied logs, builds "
  + "the structural / rarity / semantic indexes, runs the agentic loop and prints a "),
  B("cited, causally-ordered root-cause narrative"),
  T(". It answers both validation scenarios correctly "), B("with or without"),
  T(" an LLM key.")]));

c.push(H1("2. Prerequisites"));
c.push(bullet("Python 3.10+ (developed on 3.10.6, Windows)."));
c.push(bullet("Node.js — only for regenerating the deliverable documents, not for running the engine."));
c.push(bullet([T("Optional: a free Google AI Studio key ("), code("GOOGLE_API_KEY"),
  T(") for LLM-written narratives. Without it the engine uses its deterministic narrative.")]));

c.push(H1("3. Setup"));
c.push(...codeBlock([
  "cd rca-engine",
  "python -m venv .venv && .venv\\Scripts\\activate     # Windows",
  "pip install -r requirements.txt",
  "",
  "copy .env.example .env        # then paste a free key into GOOGLE_API_KEY",
]));
c.push(P([B("Note. "),
  T("sentence-transformers / chromadb (the optional semantic layer) pull in torch. They are "
   + "only needed for the --vectors flag; both validation scenarios are solved by the "
   + "deterministic + rarity path and need neither.")]));

c.push(H1("4. Running the Two Validation Scenarios"));
c.push(H3("Scenario 1 — chronological trigger extraction"));
c.push(...codeBlock([
  "python -m rca.cli investigate data/production_incident_01.log \\",
  "  -q \"What caused the 503 errors for TENANT-X around 16:10?\"",
]));
c.push(H3("Scenario 2 — high-volume noise demultiplexing"));
c.push(...codeBlock([
  "python -m rca.cli investigate data/auth_rate_limit_noise.log \\",
  "  -q \"Identify any system failures impacting TENANT-Z during the authentication volume spike.\"",
]));
c.push(H3("Corpus profile & web UI"));
c.push(...codeBlock([
  "python -m rca.cli profile data/production_incident_01.log   # deterministic profile",
  "streamlit run src/rca/webapp.py                             # timeline + evidence UI",
]));
c.push(P([T("Set "), code("PYTHONPATH=src"),
  T(" if running without an editable install. Each investigation makes at most one LLM call "
   + "(synthesis); the planner defaults to a deterministic heuristic.")]));

c.push(H1("5. Repository Layout"));
c.push(table(
  ["Path", "Contents"],
  [
    ["src/rca/ingest/", "reader · parser · drain_miner · normalize (deterministic pipeline)"],
    ["src/rca/store/", "schema · duckdb_store · vector_store (three indexing planes)"],
    ["src/rca/agent/", "llm_provider · tools · prompts · graph (LangGraph loop + BYOK)"],
    ["src/rca/synth/", "causal · report · lineage (verifiable chain + anti-hallucination)"],
    ["src/rca/", "cli.py · webapp.py · pipeline.py · config.py"],
    ["tests/", "test_ingest · test_scenarios (assert both scenarios with no LLM)"],
    ["data/", "the two provided log files"],
    ["deliverables/, diagrams/", "generated documents and rendered architecture diagrams"],
  ],
  [2600, 6760]));

c.push(H1("6. Execution Flow (Code Path)"));
c.push(num([code("pipeline.build_engine()"), T(" — ingest each file → DuckDBStore → optional vector index → RCAEngine.")]));
c.push(num([code("ingest.normalize.ingest_file()"), T(" — reader (coalesce traces) → parser (regex) → Drain3 → LogEvent records.")]));
c.push(num([code("agent.graph.RCAEngine.investigate()"), T(" — LangGraph plan → retrieve → reflect → synthesize.")]));
c.push(num([code("synth.causal.build_causal_chain()"), T(" — deterministic trigger / transition / precursor / symptom classification.")]));
c.push(num([code("synth.report.synthesize()"), T(" — deterministic narrative, optionally re-written by the LLM and citation-verified.")]));

c.push(H1("7. Testing"));
c.push(...codeBlock([
  "pytest -q",
  "# 8 tests: ingestion contract + both validation scenarios, all with NO LLM key.",
]));
c.push(table(
  ["Test", "Asserts"],
  [
    ["test_ingest", "100% parse, stack-trace coalescing, 503 flood → 1 template, trigger template unique"],
    ["test_scenarios (S1)", "Root cause = connection-pool timeout; 503s are symptoms; chronology verified; trigger line cited"],
    ["test_scenarios (S2)", "Root cause = TENANT-Z token-validation timeout; TENANT-Y 429 flood excluded as noise"],
  ],
  [2600, 6760]));

c.push(H1("8. Configuration & Security"));
c.push(bullet([T("All runtime knobs are environment variables (see "), code(".env.example"),
  T("); no key is ever hardcoded.")]));
c.push(bullet([T("Swap the model with "), code("RCA_LLM_PROVIDER=gemini|openrouter|ollama"), T(".")]));
c.push(bullet([T("Dependencies pinned in "), code("requirements.txt"), T("; metadata + entrypoint in "), code("pyproject.toml"), T(".")]));
c.push(bullet([code(".env"), T(" is git-ignored; the Ollama path keeps data fully on-machine for confidentiality.")]));

write(buildDoc({ title: "Prototype Code & How-to-Run Guide", footerId: "COD-RCA-001", children: c }),
  path.resolve(__dirname, "03_Prototype_Code_and_How_to_Run.docx"));
