# Conceptual Architecture Blueprint — Agentic RCA Engine

This blueprint shows *how the pieces fit*. The companion [DESIGN.md](DESIGN.md) explains *why*.
The single organising idea: **a deterministic reduction stage collapses the haystack before any
AI touches it; the AI then plans retrieval and narrates verified evidence.**

---

## 1. System overview

```mermaid
flowchart TB
    subgraph SRC["Raw multi-tenant log streams"]
        L1["production_incident_01.log"]
        L2["auth_rate_limit_noise.log"]
        L3["...live volumes"]
    end

    subgraph DET["① DETERMINISTIC PLANE — no LLM, O(n), &lt;0.2s / 5k lines"]
        R["Reader<br/>(coalesce stack traces)"]
        P["Parser<br/>(regex → fields, RAW fallback)"]
        D["Drain3 miner<br/>(template_id + masking)"]
        N["Normalize<br/>(UTC, enums, params)"]
        R --> P --> D --> N
    end

    subgraph STORE["② STORAGE & INDEXING"]
        DB[("DuckDB<br/>events table<br/>idx: tenant, ts, level, template")]
        RAR["Rarity plane<br/>(per-tenant template counts)"]
        VEC[("Chroma<br/>template catalog vectors<br/>(optional)")]
    end

    subgraph AGENT["③ AGENTIC PLANE — LangGraph"]
        PL["plan"] --> RT["retrieve"] --> RF["reflect"] --> SY["synthesize"]
    end

    Q["Engineer NL query"] --> PL
    SRC --> DET --> STORE
    STORE <--> AGENT
    SY --> OUT["Cited, causally-ordered RCA"]
```

---

## 2. The deterministic ↔ LLM boundary (the core decision)

```mermaid
flowchart LR
    subgraph DETER["DETERMINISTIC (exact, cheap, reproducible)"]
        A["Parse"] --> B["Template-mine"] --> C["Partition by tenant"]
        C --> D["Rank by rarity"] --> E["Order by time<br/>trigger vs symptom"]
    end
    subgraph LLMS["LLM (only where language/judgement is needed)"]
        F["Plan: NL → retrieval params"]
        G["Synthesize: evidence → prose"]
    end
    E -- "≤40 cited rows" --> G
    Q["query"] --> F --> D
    G --> ANS["answer + citations"]
    G -. "citation check fails" .-> DETNARR["deterministic narrative<br/>(safe fallback)"]
```

**Rule:** anything exact (parse, filter, count, sort, classify-by-time) is code; only query
*interpretation* and *narration* are the model's — and narration is verified against retrieved
evidence before it is trusted.

---

## 3. Agent retrieval loop (state machine)

```mermaid
stateDiagram-v2
    [*] --> plan
    plan --> retrieve: tenant_id, intent, symptom_terms
    retrieve --> reflect: causal chain + evidence
    reflect --> retrieve: nothing found → widen scope (once)
    reflect --> synthesize: chain ready
    synthesize --> [*]: cited narrative

    note right of plan
      LLM or regex heuristic.
      Rejects invented tenants.
    end note
    note right of retrieve
      Deterministic tools only.
      Full-timeline / symptom-anchored
      (defeats the "16:10" trap).
    end note
    note right of synthesize
      Evidence-grounded.
      Citations verified → else
      deterministic fallback.
    end note
```

---

## 4. Scenario 1 — chronological trigger extraction

```mermaid
sequenceDiagram
    participant E as Engineer
    participant A as Agent
    participant DB as DuckDB (rarity)
    E->>A: "What caused the 503s for TENANT-X around 16:10?"
    A->>DB: rare_templates(tenant=TENANT-X, level≥WARN)
    DB-->>A: T10 ConnectionTimeoutException (n=1) ▲ ranked ABOVE
    DB-->>A: T(breaker) CLOSED→OPEN (n=1)
    DB-->>A: pool utilization >90% (n=25, BEFORE trigger → precursor)
    DB-->>A: 503 flood (n=237, AFTER trigger → symptom)
    A->>DB: causal_window(trigger) → verify trigger precedes flood
    A-->>E: ROOT CAUSE = DB connection-pool timeout → breaker OPEN → 503 symptoms<br/>(chronology verified, cited to line 3252 + stack trace)
```

The 237-line flood is reduced to a single template row; rarity floats the 1-line cause to the
top; chronology proves it preceded the symptoms.

---

## 5. Scenario 2 — high-volume noise demultiplexing

```mermaid
flowchart TB
    Q["Query: failures impacting TENANT-Z?"] --> PART{"Partition by tenant_id"}
    PART -->|"TENANT-Y: 2,399 lines<br/>1,799 × 429 flood"| DROP["excluded — named as<br/>unrelated noise"]
    PART -->|"TENANT-Z: 201 lines"| ZED["scan TENANT-Z only"]
    ZED --> STRIP["drop 199 benign INFO<br/>token-validations"]
    STRIP --> NEEDLE["2 needles remain:<br/>ERROR token-validation timeout (line 2451)<br/>WARN SLA breach 2500ms (line 2456)"]
    NEEDLE --> ANS["TENANT-Z root cause,<br/>TENANT-Y flood explicitly excluded"]
```

Tenant partitioning makes the buried 2-line anomaly trivially findable and keeps the flood out
of the context window entirely — no false-positive correlation.

---

## 6. Data lineage & anti-hallucination

```mermaid
flowchart LR
    RAW["raw line + line_no"] --> EV["LogEvent.event_id"]
    EV --> TOOL["tool returns EvidenceRow<br/>(event_id, line_no, source_file)"]
    TOOL --> CTX["bounded evidence block (≤40)"]
    CTX --> LLM["LLM narration<br/>'cite event N'"]
    LLM --> CHK{"every cited id<br/>∈ retrieved set?"}
    CHK -->|yes| TRUST["trusted answer"]
    CHK -->|no| FALL["revert to deterministic narrative"]
```

Every sentence in the final report is traceable to a verbatim log line; an unsupported citation
can never survive into the answer.

---

## 7. Deployment view (prototype → production)

```mermaid
flowchart TB
    subgraph PROTO["Prototype (this repo)"]
        CLI["Typer CLI"] --- WEB["Streamlit UI"]
        CLI --> ENG["RCAEngine"]
        WEB --> ENG
        ENG --> EDB[("DuckDB :memory:")]
        ENG --> ECH[("Chroma in-proc")]
        ENG --> GEM["Gemini / Ollama (BYOK)"]
    end
    subgraph PROD["Production evolution"]
        ING["Streaming ingest<br/>(Kafka + Drain3 snapshots)"] --> CH[("ClickHouse / DuckDB-on-S3")]
        ING --> VDB[("Managed vector DB,<br/>per-tenant namespaces")]
        API["RCA API / chat"] --> ORCH["LangGraph workers"]
        ORCH --> CH
        ORCH --> VDB
        ORCH --> LLMP["LLM pool<br/>(per-tenant quota + cache)"]
    end
    PROTO -. "same interfaces" .-> PROD
```
