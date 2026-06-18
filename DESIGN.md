# Technical Design Document — Agentic RCA Engine for Multi-Tenant Log Intelligence

**Author:** AI Solution Engineering · **Status:** Prototype + design · **Audience:** Platform / SRE / Applied-AI engineering

---

## 0. Executive summary

We are building the Root-Cause-Analysis (RCA) engine for an enterprise log-intelligence
platform. Engineers ask natural-language questions during a live incident
("*What caused the 503s for TENANT-X?*") and the system returns a **cited, causally-ordered
root-cause narrative** drawn from high-volume, multi-tenant, interleaved log streams.

The design rests on one load-bearing thesis, which we validated empirically against the two
provided datasets before writing a line of architecture:

> **Deterministic structural reduction must precede every semantic/LLM operation.**
> Partition-by-tenant + log-template mining + rarity scoring + chronological ordering turn a
> 5,000-line haystack into a ~10-row evidence set *before* a token is spent. Naive
> "embed-everything + vector-RAG" fails both validation scenarios because the dense, repeated
> *symptoms* dominate the embedding space and bury the rare *cause*.

The LLM is deliberately confined to two narrow jobs — **query planning** and
**evidence-grounded synthesis** — and is never shown raw logs. The engine produces a fully
correct answer for both scenarios **with no LLM at all** (deterministic narrative path); the
model only improves readability, and any answer it produces is citation-verified against
retrieved evidence.

---

## 1. The data, read first (evidence-driven design)

Everything below is grounded in line-by-line analysis of the two files, not assumptions.

### Shared grammar
```
<ISO-8601 ts> [TENANT-ID] <LEVEL> [<java.logger.Component>] <message>
        (+ optional indented "    at com.x.Y(File.java:NN)" stack-trace continuations)
```
The format is highly regular: **100% of lines parse with one regex** (measured: 0 RAW
fallbacks across 10,000 lines), and stack traces are multi-line and must be coalesced into
their parent event.

### Scenario 1 — `production_incident_01.log` (12:00:00–12:04:34, tenants A–F + X)
| Phase | Signature | Component | Count | First seen |
|---|---|---|---|---|
| Precursor | `connection pool utilization exceeding 90%` (WARN) | `db.DataSource` | 25 | 12:02:55.540 |
| **ROOT TRIGGER** | `pool.ConnectionTimeoutException ...` (+3-line trace) | `db.DataSource` | **1** | 12:02:58.378 |
| Transition | `CircuitBreaker State Changed: CLOSED → OPEN` | `circuit.Breaker` | **1** | 12:02:58.408 |
| **Symptom flood** | `503 Service Unavailable. CircuitBreaker OPEN` (ERROR) | `gateway.Ingress` | **237** | 12:02:58.661 |

The cause is **1 line**; the symptoms are **237 lines** that arrive *after* it. Note the
sample query says "around **16:10**" but the incident is at **12:02** — a deliberate trap:
the engine must anchor on the *symptom signature*, not the user's literal clock time.

### Scenario 2 — `auth_rate_limit_noise.log` (14:00–14:02)
| Tenant | Role | Lines | Critical content |
|---|---|---|---|
| TENANT-Y | **Noise flood** | 2,399 | 1,799 × `429 Too Many Requests` + 600 rate-limit WARNs |
| TENANT-Z | **Silent victim** | 201 | 199 benign `Token validated` INFO **+ exactly 2 needles**: `ERROR token-validation timeout` (14:01:07.787) and `WARN SLA breach 2500ms` |

The needle is **2 lines among 5,002**, sitting *literally between* TENANT-Y 429 lines.
Embedding all lines makes TENANT-Y's 1,799 near-identical vectors a dense cluster that
dominates any top-k search.

---

## 2. Task 1 — Data Ingestion, Parsing & Representation

### 2.1 Data modelling & multi-tenant isolation
A single canonical record — `LogEvent` ([schema.py](src/rca/store/schema.py)) — normalises
every line. Variable fields live in a free-form `params` JSON so a never-before-seen log
shape lands without a migration (additive schema). Key fields: `event_id` (stable citation
handle), `raw_line_no` (lineage), `ts`, `tenant_id` (**partition key**), `level`,
`component`, `template_id` (Drain3 cluster), `template_text`, `params`, `stack_trace`.

**Isolation** is enforced at the storage layer: `tenant_id` is an indexed filter on every
query path and a metadata facet on every vector. One tenant's flood can therefore never
inflate another tenant's retrieval cost or pollute its context — this is the entire
mechanism behind Scenario 2.

### 2.2 Processing pipeline & the deterministic ↔ LLM boundary
```
RAW LOG ─► D1 Reader (coalesce stack traces)         ─┐
        ─► D2 Parser (regex → fields, RAW fallback)   │ DETERMINISTIC, single O(n) pass
        ─► D3 Drain3 (template_id + masked template)  │ ~5k lines in <0.2s, CPU-only,
        ─► D4 Normalize (UTC, enums, params)          │ zero LLM cost
        ─► D5 Load → DuckDB (partition/sort by tenant,ts)
        ─► D6 Index: DuckDB indexes + rarity table + (opt) template-vector index ─┘
        ═══════════════════════════ boundary ═══════════════════════════
        ─► L1 Plan: NL query → retrieval plan            (LLM, 1 call — or heuristic)
        ─► L2 Retrieve: deterministic tools build chain  (NO LLM — exact SQL)
        ─► L3 Synthesize: cited narrative from evidence  (LLM, 1 call — or template)
```

**Why this boundary.** Parsing-by-LLM would mean ~5,000 calls per file — impossible on a free
tier (15 RPM) and needlessly slow and non-deterministic. Parsing is a solved deterministic
problem here. Conversely, *causality* and *natural language* are where the LLM earns its
place — but even causality we compute deterministically (§3.3) and let the LLM only narrate,
because a hallucinated causal claim during an incident is worse than no claim.

### 2.3 Trade-offs
| Dimension | Decision | Consequence |
|---|---|---|
| Latency | Deterministic pre-filter to ≤40 rows | LLM context tiny → fast, fits free-tier TPM |
| Throughput | Single-pass streaming ingest + columnar store | 10k lines in ~0.2s on a laptop |
| Compute cost | Embeddings over *templates only* (dozens), not lines (thousands) | ~100× fewer vectors |
| Operational cost | ~3–6 LLM calls per investigation regardless of corpus size | Stays inside free quotas |
| Accuracy | Causality from timestamps + frequency, not model intuition | Reproducible, auditable |

---

## 3. Task 2 — Agentic Diagnostics & Evidence Retrieval

### 3.1 Storage & indexing — three planes over one table
- **Structural plane (DuckDB):** indexed exact filters on temporal (`ts BETWEEN`),
  relational/spatial (`tenant_id`, `component`, `level`) and aggregate (`GROUP BY template_id`)
  dimensions. ([duckdb_store.py](src/rca/store/duckdb_store.py))
- **Rarity plane (derived):** per-tenant template counts → inverse-frequency ranking. A single
  SQL window query surfaces the count=1 `ConnectionTimeoutException` *above* the 237-line flood.
- **Semantic plane (Chroma, optional):** embeddings over the **distinct template catalog** so a
  flood contributes one vector, not thousands. ([vector_store.py](src/rca/store/vector_store.py))

### 3.2 The autonomous retrieval & execution loop
A LangGraph state machine — `plan → retrieve → reflect → synthesize`
([graph.py](src/rca/agent/graph.py)) — over six deterministic, lineage-stamped tools
([tools.py](src/rca/agent/tools.py)):
`structured_query`, `rare_templates`, `template_frequencies`, `semantic_search`,
`causal_window`, `fetch_evidence`. Every tool returns `EvidenceRow`s carrying `event_id` +
`raw_line_no` + `source_file` — the agent can only ever cite what it actually retrieved.

- **plan** — LLM (or, with no key, a regex heuristic) extracts `tenant_id`, `intent`,
  `symptom_terms`, `time_hint`. An invented/unknown tenant is rejected.
- **retrieve** — builds the causal chain (§3.3); we scan the tenant's **full timeline** and
  anchor on the symptom signature, which is what defeats the "around 16:10" trap.
- **reflect** — if the named tenant yielded nothing, widen across tenants once.
- **synthesize** — constrained narration, then citation verification (§3.4).

### 3.3 Verifiable causal chains — trigger vs symptom (deterministic)
([causal.py](src/rca/synth/causal.py)) Classification is arithmetic, not opinion:
- **TRIGGER** = the chronologically earliest, *low-frequency*, high-severity event.
- **TRANSITION** = state-change events (circuit breaker) between cause and flood.
- **SYMPTOM** = *high-frequency* templates whose first occurrence is **at/after** the trigger.
- **PRECURSOR** = high-frequency templates *before* the trigger (e.g. pool-pressure warnings) —
  split from symptoms by chronology, not just count.

A chain is only emitted as verified when `trigger.ts ≤ earliest_symptom.first_seen`, making
cause→effect a checkable invariant (`chronology_verified` flag in the output).

### 3.4 Data lineage, anti-hallucination, context management
- **Lineage:** every claim cites `event N` → resolvable to `file:line`. Verbatim text and stack
  traces travel with the evidence.
- **Anti-hallucination ("evidence-or-silence"):** the synthesis prompt forbids uncited claims;
  [lineage.py](src/rca/synth/lineage.py) then *verifies* every cited `event_id` was actually
  retrieved and, on any unsupported citation, **reverts to the deterministic narrative**. The
  facts always come from the deterministic chain; the LLM cannot introduce new ones.
- **Context constraints:** deterministic reduction caps evidence at `max_evidence_rows` (40) —
  the LLM never sees the 5k-line file, so context stays small and on-budget.
- **Noise demultiplexing:** the engine names any concurrent cross-tenant flood explicitly as
  *unrelated noise* (Scenario 2: "TENANT-Y emitted ×1799 429s … excluded as unrelated to
  TENANT-Z"), preventing false-positive correlation.

---

## 4. Free / open-source stack (BYOK)
| Layer | Choice | Free terms / rationale |
|---|---|---|
| LLM | Gemini 2.5 Flash (primary) · OpenRouter free · Ollama | 15 RPM / 1,500 RPD / 1M TPM free; swap via `RCA_LLM_PROVIDER`; Ollama = fully offline (confidentiality) |
| Orchestration | LangGraph + langchain-core | Inspectable stateful agent loop, not bespoke control flow |
| Template mining | Drain3 (logpai) | Production streaming Drain; the noise→signal engine |
| Structural store | DuckDB | Embedded columnar OLAP, zero-config |
| Vector store | ChromaDB (+ MiniLM, local) | Template-only embeddings, offline, free |
| Schema | Pydantic v2 | Typed event + tool IO |
| Interface | Typer CLI + Streamlit | Reproducible demo + visual evidence/timeline |

No credential is hardcoded; keys are read from `.env` only ([config.py](src/rca/config.py)).
If no key is present the engine runs end-to-end on its deterministic path.

---

## 5. Validation results (measured)
Run with **no LLM key** (pure deterministic path); all assertions in
[tests/test_scenarios.py](tests/test_scenarios.py) pass.

- **Scenario 1:** root cause = `pool.ConnectionTimeoutException` (`db.DataSource`, event 3252,
  line 3252) with stack trace; circuit-breaker `CLOSED→OPEN` captured as transition; 237×503
  classified as downstream symptom; **chronology verified**; "16:10" trap handled (anchored on
  12:02 symptom burst).
- **Scenario 2:** root cause = `token-validation timeout` for **TENANT-Z** (event 2451, line
  2451) + SLA breach; **TENANT-Y's 1,799-line 429 flood explicitly excluded as noise**; all
  cited evidence is TENANT-Z only.
- **Ingestion:** 5,000 events, 12 templates, ~0.2s parse; 0 unparsed lines; 503 flood collapses
  to a single template.

---

## 6. Production hardening (beyond the prototype)
- Swap embedded DuckDB → distributed columnar (ClickHouse / DuckDB-on-object-store) and Chroma →
  a managed vector DB; partition physically per tenant.
- Drain3 persistent state snapshots for streaming ingest; schema registry for params drift.
- Per-tenant rate-limit / quota isolation on the LLM layer; response + plan caching.
- Confidence scoring + human-in-the-loop escalation when `chronology_verified` is false.
- Observability: emit the agent's tool-call trace and evidence set as an audit record per query.
