// Conceptual Architecture Blueprint
const path = require("path");
const L = require("./lib");
const { T, B, code, H1, H2, P, bullet, figure, titlePage, buildDoc, toc, write, DIAG } = L;
const d = (n) => path.join(DIAG, `diagram_${n}.png`);

const c = [];
c.push(...titlePage("Conceptual Architecture Blueprint",
  "Agentic Root-Cause-Analysis Engine", "ARC-RCA-001",
  "A component and data-flow view of the RCA engine: a deterministic reduction stage that "
  + "collapses high-volume multi-tenant logs into a small, cited evidence set, and an agentic "
  + "stage that plans retrieval and narrates verified findings."));
c.push(...toc());

c.push(H1("1. Purpose & Organising Idea"));
c.push(P([T("This blueprint shows how the components fit together; the companion "),
  B("Technical Design Document"),
  T(" explains why. The single organising idea:")]));
c.push(P([B("A deterministic reduction stage collapses the haystack before any AI touches it; "
  + "the AI then plans retrieval and narrates verified evidence."), ],
  { alignment: "center" }));

c.push(H1("2. System Overview"));
c.push(P("Raw multi-tenant streams flow through a deterministic ingestion plane into a "
  + "three-plane store; a LangGraph agent queries that store and synthesises a cited answer. "
  + "No raw log line ever reaches the LLM."));
c.push(...figure(d(1), "Figure 1 — End-to-end system overview: deterministic plane → storage & "
  + "indexing → agentic plane."));
c.push(L.pageBreak());

c.push(H1("3. The Deterministic ↔ LLM Boundary"));
c.push(P("The core design decision. Anything exact (parse, filter, count, sort, classify by "
  + "time) is code; only query interpretation and narration are the model’s — and narration "
  + "is verified against retrieved evidence before it is trusted."));
c.push(...figure(d(2), "Figure 2 — Division of labour: deterministic operations feed a bounded, "
  + "cited evidence set to the LLM; failed citation checks fall back to a deterministic narrative."));

c.push(H1("4. Agent Retrieval Loop"));
c.push(P([T("The agent is a four-state machine. "), B("plan"),
  T(" extracts retrieval parameters (rejecting invented tenants); "), B("retrieve"),
  T(" runs deterministic tools and is symptom-anchored to defeat the “16:10” trap; "),
  B("reflect"), T(" widens scope once if nothing surfaced; "), B("synthesize"),
  T(" produces an evidence-grounded, citation-verified narrative.")]));
c.push(...figure(d(3), "Figure 3 — LangGraph state machine: plan → retrieve → reflect → synthesize."));
c.push(L.pageBreak());

c.push(H1("5. Scenario 1 — Chronological Trigger Extraction"));
c.push(P("Rarity ranking floats the 1-line connection-pool timeout above the 237-line 503 "
  + "flood; a causal-window check proves the trigger preceded the symptoms."));
c.push(...figure(d(4), "Figure 4 — TENANT-X: isolating the low-frequency initiator from the "
  + "dense downstream 503 flood."));

c.push(H1("6. Scenario 2 — High-Volume Noise Demultiplexing"));
c.push(P("Tenant partitioning makes the buried 2-line TENANT-Z anomaly trivially findable and "
  + "keeps TENANT-Y’s 1,799-line flood out of the context window entirely."));
c.push(...figure(d(5), "Figure 5 — TENANT-Z vs TENANT-Y: partition-first demultiplexing avoids "
  + "false-positive correlation."));
c.push(L.pageBreak());

c.push(H1("7. Data Lineage & Anti-Hallucination"));
c.push(P("Every sentence in the final report is traceable to a verbatim log line; an "
  + "unsupported citation can never survive into the answer."));
c.push(...figure(d(6), "Figure 6 — Lineage chain: raw line → event_id → tool → bounded context → "
  + "narration → citation check → trusted answer or deterministic fallback."));

c.push(H1("8. Deployment View (Prototype → Production)"));
c.push(P("The prototype runs fully on a laptop (embedded DuckDB, in-process Chroma, BYOK LLM). "
  + "The same interfaces scale to a streaming, multi-worker production topology."));
c.push(...figure(d(7), "Figure 7 — Evolution from the local prototype to a production "
  + "streaming/serving topology behind identical interfaces."));

c.push(H1("9. Component Responsibilities (Quick Reference)"));
c.push(L.table(
  ["Module", "Responsibility"],
  [
    ["ingest/ (reader, parser, drain_miner, normalize)", "Deterministic raw→canonical LogEvent pipeline"],
    ["store/ (schema, duckdb_store, vector_store)", "Three indexing planes: structural, rarity, semantic"],
    ["agent/ (llm_provider, tools, prompts, graph)", "BYOK provider + retrieval tools + LangGraph loop"],
    ["synth/ (causal, report, lineage)", "Verifiable causal chain + cited report + citation guard"],
    ["cli.py / webapp.py / pipeline.py", "Interfaces and one-call wiring"],
  ],
  [4000, 5360]));

write(buildDoc({ title: "Conceptual Architecture Blueprint", footerId: "ARC-RCA-001", children: c }),
  path.resolve(__dirname, "02_Conceptual_Architecture_Blueprint.docx"));
