// Technical Design Document — enriched, senior-authored.
const path = require("path");
const L = require("./lib");
const { T, B, code, H1, H2, H3, P, bullet, num, codeBlock, table, figure,
        titlePage, buildDoc, toc, write, DIAG } = L;

const c = [];
c.push(...titlePage("Technical Design Document",
  "Agentic Root-Cause-Analysis Engine", "TDD-RCA-001",
  "Design for an engine that lets on-call engineers diagnose outages by asking plain-English "
  + "questions over high-volume, multi-tenant log streams — returning a cited, causally-ordered "
  + "root cause rather than a wall of matching log lines."));
c.push(...toc());

/* ─────────────────────────────── 1. Executive summary ───────────────────── */
c.push(H1("1. Executive Summary"));
c.push(P([B("What this is. "),
  T("The design for the Root-Cause-Analysis (RCA) engine inside an enterprise log-intelligence "
   + "platform. During a live incident an engineer asks a question in plain English — "),
  code("“What caused the 503s for TENANT-X around 16:10?”"),
  T(" — and the engine answers with a "),
  B("cited, causally-ordered root cause"),
  T(", not a page of matching log lines.")]));
c.push(P([B("The core problem. "),
  T("In a multi-tenant platform the true cause of an outage is almost always a "),
  B("rare, low-volume event"),
  T(" that is buried under a flood of high-volume "), T("symptoms", { italics: true }),
  T(" — and often under an unrelated neighbour tenant's noise. A naïve “index everything and "
   + "let an LLM read it” approach drowns in that volume: the repeated symptoms dominate both "
   + "the retrieved context and any vector search, and the one line that matters is never seen.")]));
c.push(P([B("The approach. "),
  T("Put a deterministic reduction stage in front of the model. Partitioning by tenant, mining "
   + "log templates, ranking by rarity and ordering by time collapse ~5,000 lines to roughly ten "
   + "cited rows "), B("before a single token is spent"),
  T(". The LLM is then used only for what it is uniquely good at — understanding the question "
   + "and writing a readable, grounded explanation. Causality itself is computed, not guessed.")]));
c.push(P([B("Result. "),
  T("Both required validation scenarios are answered correctly, including the case where the "
   + "decisive evidence is a single line among thousands. The engine works end-to-end even with "
   + "no LLM available (a deterministic narrative), and when a model is configured every "
   + "generated sentence is verified against retrieved evidence before it is shown.")]));

c.push(H2("1.1 How this document is organised"));
c.push(table(["Requirement from the brief", "Addressed in"],
  [
    ["Task 1 — Data ingestion, parsing & representation", "§8"],
    ["Task 2 — Agentic diagnostics & evidence retrieval", "§9"],
    ["Scenario 1 — chronological trigger extraction", "§5.2, §10.1"],
    ["Scenario 2 — high-volume noise demultiplexing", "§5.3, §10.2"],
    ["Deterministic vs LLM boundary; performance/cost trade-offs", "§6, §8.2, §8.3"],
    ["Data lineage, hallucination prevention, context limits", "§9.6"],
    ["Alternatives weighed and rejected", "§7"],
    ["BYOK, dependency minimisation, free/OSS stack", "§13"],
  ], [5400, 3960]));
c.push(L.pageBreak());

/* ─────────────────────────── 2. Problem statement ───────────────────────── */
c.push(H1("2. Problem Statement & Context"));
c.push(P("During a production incident, the scarcest resource is the responder's attention. "
  + "The platform ingests high-volume, interleaved log streams from many tenants; when something "
  + "breaks, the volume does not help — it actively hides the cause. Three properties of the "
  + "domain make this hard, and the design is shaped by all three:"));
c.push(bullet([B("Cause is rare; symptoms are loud. "),
  T("A single connection-pool timeout can trip a circuit breaker and emit hundreds of identical "
   + "downstream 503s in seconds. The hundreds are noise; the one is the answer. Frequency is "
   + "inversely correlated with diagnostic value.")]));
c.push(bullet([B("Tenants are interleaved. "),
  T("One tenant's volumetric event (e.g. an authentication rate-limit flood) can outnumber "
   + "another tenant's critical-but-quiet failure by an order of magnitude in the same time "
   + "window, on the same lines. Without hard isolation, the loud tenant masks the quiet one.")]));
c.push(bullet([B("Responders think in questions, not queries. "),
  T("An engineer wants to ask “what caused this?”, not hand-craft a log query language under "
   + "pressure — and they need an answer they can trust and act on, with the evidence attached.")]));
c.push(P([B("Goal restated. "),
  T("Reduce time-to-diagnosis by turning a natural-language question into a verifiable causal "
   + "chain — distinguishing the historical trigger from its downstream symptoms — while remaining "
   + "robust to volume, multi-tenant noise, and the imperfect information in the question itself "
   + "(for example an approximate or wrong timestamp).")]));

/* ─────────────────────────── 3. Goals / non-goals ───────────────────────── */
c.push(H1("3. Goals & Non-Goals"));
c.push(H3("In scope (goals)"));
c.push(bullet("Natural-language incident questions answered with a cited, causally-ordered root cause."));
c.push(bullet("Strict isolation of the queried tenant from all other tenants' traffic and noise."));
c.push(bullet("Reliable separation of the low-frequency trigger from high-frequency downstream symptoms."));
c.push(bullet("Verifiable data lineage: every claim traces to a specific log line; no fabricated facts."));
c.push(bullet("Bounded, predictable cost and latency that fit free-tier LLM quotas and a single laptop."));
c.push(bullet("Graceful degradation: a correct answer even when no LLM is available."));
c.push(H3("Out of scope (non-goals, for this iteration)"));
c.push(bullet("A production ingestion fabric (Kafka, autoscaling, retention tiers) — addressed as a roadmap in §12."));
c.push(bullet("Cross-incident learning / historical RCA knowledge base — a natural follow-on, not required here."));
c.push(bullet("Alerting, ticketing and remediation actions — the engine explains; it does not act."));
c.push(bullet("Fine-tuning or training models — the design is deliberately model-agnostic and BYOK."));

/* ─────────────────────────── 4. Requirements ────────────────────────────── */
c.push(H1("4. Requirements"));
c.push(H2("4.1 Functional"));
c.push(table(["#", "Requirement"],
  [
    ["F1", "Ingest heterogeneous, multi-tenant log files and normalise them to a queryable schema."],
    ["F2", "Parse a natural-language question into tenant, intent, symptom terms and any time hint."],
    ["F3", "Retrieve the candidate root cause and supporting evidence for the queried tenant."],
    ["F4", "Classify events into trigger, transition, precursor and symptom, and order them causally."],
    ["F5", "Return a narrative that cites each claim to a concrete log line, plus the raw evidence."],
    ["F6", "Explicitly identify and exclude unrelated, concurrent noise from other tenants."],
  ], [800, 8560]));
c.push(H2("4.2 Non-functional"));
c.push(table(["Attribute", "Target / decision"],
  [
    ["Isolation", "Tenant is a hard filter on every retrieval path; one tenant's volume cannot affect another."],
    ["Latency", "Parse + index a 5k-line file in well under a second; one investigation ≈ a handful of LLM calls."],
    ["Throughput", "Single-pass O(n) ingestion; linear in log size, CPU-only."],
    ["Cost", "Fits free-tier quotas (e.g. 15 req/min, 1,500/day); embeddings run locally and free."],
    ["Trustworthiness", "No uncited claims; causal ordering is a checkable invariant, not model opinion."],
    ["Portability / BYOK", "Runs on a laptop; keys from environment only; provider is swappable."],
    ["Resilience", "If the LLM is rate-limited or absent, the engine still returns a correct deterministic answer."],
  ], [2200, 7160]));
c.push(L.pageBreak());

/* ─────────────────────────── 5. The data, read first ────────────────────── */
c.push(H1("5. The Data, Read First"));
c.push(P("Good design here follows from reading the actual logs, not from a generic template. "
  + "Both supplied files were analysed line by line; the signal-to-noise structure below is what "
  + "the architecture is built to exploit."));
c.push(H2("5.1 Shared grammar"));
c.push(P("Both files share one regular grammar, which makes deterministic parsing trivial and "
  + "removes any need for an LLM in the parsing path:"));
c.push(...codeBlock([
  "<ISO-8601 ts> [TENANT-ID] <LEVEL> [<java.logger.Component>] <message>",
  "        (+ optional indented \"    at com.x.Y(File.java:NN)\" stack-trace lines)",
]));
c.push(P([T("Measured: "), B("100% of lines parse with a single regular expression"),
  T(" (zero unparsed fallbacks across 10,000 lines). Multi-line stack traces are coalesced into "
   + "their parent event so they are never mistaken for separate records — and the trace itself "
   + "becomes part of the cited evidence.")]));
c.push(H2("5.2 Scenario 1 — production_incident_01.log (12:00:00–12:04:34)"));
c.push(P("Out of 5,003 lines, the true story is roughly 27. The cause is a single line; the "
  + "symptoms are 237 lines that arrive after it:"));
c.push(table(["Phase", "Signature", "Component", "Count", "First seen"],
  [
    ["Precursor", "connection pool utilization > 90% (WARN)", "db.DataSource", "25", "12:02:55.540"],
    ["ROOT TRIGGER", "pool.ConnectionTimeoutException (+ trace)", "db.DataSource", "1", "12:02:58.378"],
    ["Transition", "CircuitBreaker CLOSED → OPEN", "circuit.Breaker", "1", "12:02:58.408"],
    ["Symptom flood", "503 Service Unavailable, breaker OPEN", "gateway.Ingress", "237", "12:02:58.661"],
  ], [1450, 3360, 1750, 850, 1950]));
c.push(P([B("The “16:10” trap. "),
  T("The sample question says “around 16:10”, but the incident is at 12:02. A system that hard-"
   + "filters on the stated clock time finds nothing. The design therefore anchors retrieval on "
   + "the "), B("symptom signature"),
  T(" and scans the tenant's whole timeline — the time hint is advisory, never a blind filter.")]));
c.push(H2("5.3 Scenario 2 — auth_rate_limit_noise.log (14:00–14:02)"));
c.push(table(["Tenant", "Role", "Lines", "Critical content"],
  [
    ["TENANT-Y", "Noise flood", "2,399", "1,799 × 429 Too Many Requests + ~600 rate-limit WARNs"],
    ["TENANT-Z", "Silent victim", "201", "199 benign INFO + exactly 2 needles: ERROR token-validation timeout (14:01:07.787) and WARN SLA breach 2500ms"],
  ], [1250, 1450, 950, 5710]));
c.push(P([T("The needle is "), B("two lines among 5,002"),
  T(", sitting between TENANT-Y's 429 lines. Embedding every line would make TENANT-Y's 1,799 "
   + "near-identical vectors a dense cluster that dominates any similarity search — the exact "
   + "failure mode the design must prevent.")]));
c.push(H2("5.4 The two lessons the data forces"));
c.push(num([B("Deterministic structural filtering must precede semantic/LLM retrieval. "),
  T("Partition-by-tenant plus template de-duplication makes both needles trivially findable.")]));
c.push(num([B("Rarity ≈ diagnostic value; chronology separates trigger from symptom. "),
  T("Collapsing 237 identical 503s into one template (count 237) turns “massive volume” into a "
   + "single low-information row, while the count-1 ConnectionTimeoutException stands out at once.")]));
c.push(L.pageBreak());

/* ─────────────────────────── 6. Design principles ───────────────────────── */
c.push(H1("6. Design Principles"));
c.push(bullet([B("Determinism first, LLM last. "),
  T("Everything exact — parse, partition, filter, de-duplicate, count, sort by time, classify — "
   + "is done in code and SQL. The model only interprets the question and narrates evidence.")]));
c.push(bullet([B("Reuse proven OSS; do not hand-roll. "),
  T("Drain3 for template mining, DuckDB for analytics, Chroma for vectors, LangGraph for the "
   + "agent loop, Pydantic for schema. Bespoke code is glue and domain logic only.")]));
c.push(bullet([B("Evidence or silence. "),
  T("A claim is allowed only if it is backed by a retrieved log line with its number. With no "
   + "evidence the honest answer is “insufficient evidence”, never a guess.")]));
c.push(bullet([B("Compute causality, don't ask for it. "),
  T("Trigger-versus-symptom is decided by frequency and timestamps, so the conclusion is "
   + "reproducible and auditable rather than a fluent-sounding assertion.")]));
c.push(bullet([B("Bounded by design. "),
  T("Pre-filtering caps the evidence handed to the model at a few dozen rows, which bounds "
   + "latency, token cost and the blast radius of any model error.")]));

/* ─────────────────────────── 7 (was 4). Alternatives ────────────────────── */
c.push(H1("7. Alternatives Considered & Rejected"));
c.push(P("Each rejected option is a tempting default; documenting why it fails on this data is "
  + "the substance of the design."));
c.push(table(["Option", "Why it is tempting", "Why it was rejected"],
  [
    ["Pure vector RAG over raw lines",
     "Simple; one embedding index; “just ask the LLM”.",
     "The 237 identical 503s and 1,799 identical 429s form dense clusters that dominate top-k and pollute context; the rare cause is never retrieved. Fails both scenarios."],
    ["LLM parses every log line",
     "No regex to maintain; handles any format.",
     "~5,000 calls per file: impossible on free tiers, slow, costly and non-deterministic. Parsing here is a solved exact problem."],
    ["Trust the user's timestamp and window-filter",
     "Cheap and obvious.",
     "Scenario 1's question says 16:10 but the incident is at 12:02; a hard time filter returns nothing. Must anchor on the symptom signature."],
    ["Single relational store, no template mining",
     "One database, fewer moving parts.",
     "Without template counts there is no rarity signal, so the cause cannot be floated above the flood by structural means alone."],
    ["Let the LLM decide causality from context",
     "Flexible; less code.",
     "Causal claims become unverifiable and can hallucinate during an incident. Chronology + frequency give a checkable invariant instead."],
  ], [2000, 3380, 3980]));
c.push(L.pageBreak());

/* ─────────────────────────── 8 (was 4). Task 1 ──────────────────────────── */
c.push(H1("8. Task 1 — Data Ingestion, Parsing & Representation"));
c.push(H2("8.1 Canonical schema & multi-tenant isolation"));
c.push(P([T("A single record, "), code("LogEvent"),
  T(", normalises every line. Variable fields live in a free-form "), code("params"),
  T(" object so a new log shape lands without a schema migration (additive design). Key fields:")]));
c.push(table(["Field", "Purpose"],
  [
    ["event_id", "Stable, monotonic citation handle"],
    ["raw_line_no", "Exact source line — the basis of lineage"],
    ["ts", "ISO-8601 UTC timestamp"],
    ["tenant_id", "Partition key — the foundation of isolation"],
    ["level / severity", "DEBUG…FATAL (plus a RAW fallback) and an ordinal for filtering"],
    ["component", "Logger component, e.g. com.service.db.DataSource"],
    ["template_id / template_text", "Drain3 cluster id and masked template — the de-duplication key"],
    ["params", "Extracted variables (status, db_cluster, duration, client_ip…)"],
    ["stack_trace", "Coalesced multi-line continuation lines"],
  ], [3200, 6160]));
c.push(P([B("Isolation. "),
  T("tenant_id is an indexed filter on every retrieval path and a metadata facet on every "
   + "vector. A loud tenant's volume can never inflate a quiet tenant's retrieval cost or "
   + "pollute its context — the mechanism behind Scenario 2.")]));
c.push(H2("8.2 Pipeline & the deterministic ↔ LLM boundary"));
c.push(...codeBlock([
  "RAW LOG -> D1 Reader  (coalesce stack traces)        \\",
  "        -> D2 Parser  (regex -> fields, RAW fallback)  | DETERMINISTIC, single O(n) pass",
  "        -> D3 Drain3  (template_id + masked template)  | ~5k lines < 0.2s, CPU-only,",
  "        -> D4 Normalize (UTC, enums, params)           | zero LLM cost",
  "        -> D5 Load -> DuckDB (partition/sort tenant,ts)",
  "        -> D6 Index: DuckDB indexes + rarity table + (optional) template vectors  /",
  "        ====================== boundary ======================",
  "        -> L1 Plan      NL query -> retrieval plan      (LLM 1 call, or heuristic)",
  "        -> L2 Retrieve  deterministic tools build chain (NO LLM — exact SQL)",
  "        -> L3 Synthesize cited narrative                (LLM 1 call, or template)",
]));
c.push(H2("8.3 Trade-offs"));
c.push(table(["Dimension", "Decision", "Consequence"],
  [
    ["Latency", "Deterministic pre-filter to ≤ 40 rows", "Tiny LLM context; fits free-tier limits"],
    ["Throughput", "Single-pass streaming ingest + columnar store", "~10k lines in ~0.2s on a laptop"],
    ["Compute cost", "Embed templates only (dozens), not lines (thousands)", "~100× fewer vectors"],
    ["Operational cost", "≈ 3–6 LLM calls per investigation, any corpus size", "Stays inside free quotas"],
    ["Accuracy", "Causality from timestamps + frequency", "Reproducible, auditable conclusions"],
  ], [1700, 4060, 3600]));

/* ─────────────────────────── 9 (was 5). Task 2 ──────────────────────────── */
c.push(H1("9. Task 2 — Agentic Diagnostics & Evidence Retrieval"));
c.push(H2("9.1 Three indexing planes over one table"));
c.push(bullet([B("Structural plane (DuckDB). "),
  T("Indexed exact filters on temporal (ts BETWEEN), relational (tenant_id, component, level) "
   + "and aggregate (GROUP BY template_id) dimensions.")]));
c.push(bullet([B("Rarity plane (derived). "),
  T("Per-tenant template counts → inverse-frequency ranking; one SQL window query surfaces the "
   + "count-1 trigger above the 237-line flood.")]));
c.push(bullet([B("Semantic plane (Chroma, optional). "),
  T("Embeddings over the distinct template catalogue, so a flood contributes one vector, not "
   + "thousands — open-ended discovery without context pollution.")]));
c.push(H2("9.2 The retrieval & execution loop"));
c.push(P([T("A LangGraph state machine — "),
  code("plan → retrieve → reflect → synthesize"),
  T(" — over six deterministic, lineage-stamped tools. Each returns EvidenceRow objects carrying "
   + "event_id + raw_line_no + source_file, so the agent can only cite what it actually retrieved.")]));
c.push(table(["Tool", "Role"],
  [
    ["structured_query", "Exact filter by tenant / time / level / component"],
    ["rare_templates", "Lowest-frequency WARN+ templates — candidate triggers"],
    ["template_frequencies", "Noise profile — identifies and de-prioritises floods"],
    ["semantic_search", "Vector search over the template catalogue"],
    ["causal_window", "Chronologically ordered neighbours around an anchor event"],
    ["fetch_evidence", "Verbatim line(s) + stack trace for citation"],
  ], [2600, 6760]));
c.push(H2("9.3 Verifiable causal chains — trigger vs symptom"));
c.push(P("Classification is arithmetic, not opinion:"));
c.push(bullet([B("TRIGGER "), T("= the chronologically earliest, low-frequency, high-severity event.")]));
c.push(bullet([B("TRANSITION "), T("= state changes (e.g. circuit breaker) between cause and flood.")]));
c.push(bullet([B("SYMPTOM "), T("= high-frequency templates first seen at or after the trigger.")]));
c.push(bullet([B("PRECURSOR "), T("= high-frequency templates before the trigger (e.g. pool-pressure warnings), separated from symptoms by chronology, not just count.")]));
c.push(P([T("A chain is marked "), code("chronology_verified"),
  T(" only when trigger.ts ≤ earliest_symptom.first_seen — cause-before-effect as a checkable "
   + "invariant rather than an assertion.")]));
c.push(H2("9.4 Noise demultiplexing"));
c.push(P("The engine computes the loudest concurrent template of every other tenant and names it "
  + "explicitly as unrelated noise. For Scenario 2 it states that TENANT-Y emitted 1,799 × 429 "
  + "concurrently and excludes it — preventing false-positive correlation without ever loading "
  + "that flood into the model's context."));
c.push(H2("9.5 The autonomous loop, step by step"));
c.push(bullet([B("Plan "), T("— LLM or regex heuristic extracts tenant, intent, symptom terms, time hint; an invented tenant is rejected.")]));
c.push(bullet([B("Retrieve "), T("— builds the causal chain over the tenant's full timeline (symptom-anchored, defeating the 16:10 trap).")]));
c.push(bullet([B("Reflect "), T("— if nothing surfaced for the named tenant, widen across tenants once.")]));
c.push(bullet([B("Synthesize "), T("— constrained narration over the classified chain, then citation verification (§9.6).")]));
c.push(H2("9.6 Lineage, anti-hallucination & context management"));
c.push(bullet([B("Lineage. "), T("Every claim cites “event N”, resolvable to file:line; verbatim text and stack traces travel with the evidence.")]));
c.push(bullet([B("Anti-hallucination. "),
  T("The synthesis prompt forbids uncited claims; a verifier then checks every cited event_id "
   + "was actually retrieved and, on any unsupported citation, reverts to the deterministic "
   + "narrative. Facts always originate from the deterministic chain.")]));
c.push(bullet([B("Context limits. "), T("Deterministic reduction caps evidence at ~40 rows; the model never sees the 5k-line file, so context stays small and on-budget.")]));
c.push(L.pageBreak());

/* ─────────────────────────── 10. Worked walkthroughs ────────────────────── */
c.push(H1("10. Worked Scenario Walkthroughs"));
c.push(H2("10.1 Scenario 1 — “What caused the 503s for TENANT-X?”"));
c.push(num("Plan: tenant = TENANT-X, intent = root_cause, symptom = 503; time hint 16:10 noted but not trusted."));
c.push(num("Retrieve: rarity ranking over TENANT-X surfaces ConnectionTimeoutException (count 1) and the breaker transition (count 1) above the 25 pool warnings and the 237-line 503 flood."));
c.push(num("Classify: pool warnings → precursor; ConnectionTimeoutException → trigger; CLOSED→OPEN → transition; 503s → symptom. Chronology verified (12:02:58.378 < 12:02:58.661)."));
c.push(num("Synthesize: “Root cause = DB connection-pool exhaustion → circuit breaker OPEN → 503 symptoms”, citing line 3252 and its stack trace; TENANT-F traffic flagged as unrelated."));
c.push(H2("10.2 Scenario 2 — “Any failures impacting TENANT-Z during the auth spike?”"));
c.push(num("Plan: tenant = TENANT-Z, intent = impact_scan."));
c.push(num("Retrieve: partition to TENANT-Z (drops TENANT-Y's 2,399 lines); within 201 lines, strip 199 benign INFO token validations."));
c.push(num("Classify: the two remaining WARN+ lines — token-validation timeout (trigger) and 2500ms SLA breach — are the answer."));
c.push(num("Synthesize: reports the TENANT-Z timeout + SLA breach, and explicitly excludes TENANT-Y's 1,799 × 429 flood as unrelated noise."));

/* ─────────────────────────── 11 (was 6). Validation ─────────────────────── */
c.push(H1("11. Validation Results (Measured)"));
c.push(P([T("Run with "), B("no LLM key"),
  T(" (pure deterministic path); all assertions in the automated scenario tests pass.")]));
c.push(H3("Scenario 1"));
c.push(bullet("Root cause = pool.ConnectionTimeoutException (db.DataSource, event 3252, line 3252) with stack trace."));
c.push(bullet("Breaker CLOSED→OPEN captured as the transition; 237×503 classified as downstream symptom; chronology verified."));
c.push(bullet("“16:10” trap handled by anchoring on the 12:02 symptom burst rather than the stated clock time."));
c.push(H3("Scenario 2"));
c.push(bullet("Root cause = token-validation timeout for TENANT-Z (event 2451, line 2451) + 2500ms SLA breach."));
c.push(bullet("TENANT-Y's 1,799-line 429 flood explicitly excluded as noise; every cited line is TENANT-Z only."));
c.push(H3("Ingestion & live path"));
c.push(bullet("5,000 events, 12 templates, ~0.2s parse; zero unparsed lines; the 503 flood collapses to one template."));
c.push(bullet("With a Google AI Studio key, Gemini 2.5 Flash produces the same conclusions as a clean cited narrative (LLM used = true, citations verified = true)."));

/* ─────────────────────────── 12. Risks ──────────────────────────────────── */
c.push(H1("12. Risks, Failure Modes & Mitigations"));
c.push(table(["Risk / failure mode", "Mitigation"],
  [
    ["Free-tier LLM rate limit / outage", "≤ 1 LLM call per query by default; automatic fallback to the deterministic narrative; provider is swappable (Gemini / OpenRouter / local Ollama)."],
    ["Wrong or vague time in the question", "Symptom-anchored retrieval over the full tenant timeline; the time hint never hard-filters."],
    ["Unseen / drifting log format", "Drain3 learns new templates online; unparsed lines fall back to RAW and still flow through; params are additive."],
    ["Model invents a citation", "Citations verified against the retrieved set; unsupported claims trigger a revert to the deterministic narrative."],
    ["Ambiguous causality (trigger not before flood)", "chronology_verified flag is set false and surfaced; the answer is reported as low-confidence rather than asserted."],
    ["Confidentiality of log data", "Local-first stack; the Ollama path keeps all data on-machine; keys are read from environment only."],
  ], [3300, 6060]));

/* ─────────────────────────── 13. Stack ──────────────────────────────────── */
c.push(H1("13. Free / Open-Source Stack (BYOK)"));
c.push(table(["Layer", "Choice", "Free terms / rationale"],
  [
    ["LLM", "Gemini 2.5 Flash (primary) · OpenRouter free · Ollama", "15 req/min, 1,500/day, 1M tokens/min free; swap via RCA_LLM_PROVIDER; Ollama fully offline"],
    ["Orchestration", "LangGraph + langchain-core", "Inspectable, stateful agent loop"],
    ["Template mining", "Drain3 (logpai)", "Production streaming Drain; the noise→signal engine"],
    ["Structural store", "DuckDB", "Embedded columnar OLAP, zero-config"],
    ["Vector store", "ChromaDB + MiniLM (local)", "Template-only embeddings, offline, free"],
    ["Schema", "Pydantic v2", "Typed event and tool I/O"],
    ["Interface", "Typer CLI + Streamlit", "Reproducible demo + visual evidence/timeline"],
  ], [1700, 3260, 4400]));
c.push(P([B("Security. "), T("No credential is hardcoded; keys are read from .env only. With no key, the engine runs end-to-end on its deterministic path.")]));

/* ─────────────────────────── 14. Roadmap ────────────────────────────────── */
c.push(H1("14. Production Hardening & Roadmap"));
c.push(bullet("Swap embedded DuckDB → distributed columnar (ClickHouse / DuckDB-on-object-store) and Chroma → a managed vector DB; partition physically per tenant."));
c.push(bullet("Streaming ingestion (Kafka) with Drain3 persistent state snapshots; a schema registry for params drift."));
c.push(bullet("Per-tenant LLM rate-limit / quota isolation; caching of retrieval plans and synthesised answers."));
c.push(bullet("Confidence scoring and human-in-the-loop escalation when chronology cannot be verified."));
c.push(bullet("Observability: persist the agent's tool-call trace and evidence set as an audit record per query."));
c.push(bullet("Cross-incident memory: a library of confirmed causal chains to accelerate recurring failure modes."));

/* ─────────────────────────── 15. Glossary ───────────────────────────────── */
c.push(H1("15. Glossary"));
c.push(table(["Term", "Meaning"],
  [
    ["Template (Drain3)", "A log message with its variable parts masked, e.g. “Status: <NUM>…”; identical lines collapse to one template with a count."],
    ["Trigger", "The earliest rare, high-severity event — the root cause."],
    ["Symptom", "A high-frequency event that follows the trigger; an effect, not a cause."],
    ["Precursor", "A high-frequency event before the trigger (e.g. resource pressure leading up to it)."],
    ["Rarity score", "Inverse frequency of a template within a tenant/time scope; higher = more diagnostic."],
    ["Lineage", "The traceable link from a stated claim back to a verbatim log line and number."],
    ["BYOK", "Bring Your Own Key — credentials supplied by the operator via environment variables."],
  ], [2400, 6960]));

write(buildDoc({ title: "Technical Design Document", footerId: "TDD-RCA-001", children: c }),
  path.resolve(__dirname, "01_Technical_Design_Document.docx"));
