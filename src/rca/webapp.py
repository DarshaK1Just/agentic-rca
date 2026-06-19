"""RCA Engine — Log Intelligence Console.

Run:  streamlit run src/rca/webapp.py

Sidebar: corpus selector + file-upload auto-ingest + AI engine status + session history.
Home:    how-it-works, 4 sample-prompt cards, custom query.
Result:  ← Overview back-link, metrics, verdict, causal timeline, evidence.
"""
from __future__ import annotations

import datetime
import os
import re
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import streamlit as st

from rca.agent.llm_provider import llm_available
from rca.config import settings
from rca.pipeline import build_engine
from rca import ui_theme as ui

st.set_page_config(page_title="RCA Engine — Log Intelligence Console", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)

# Safe defaults — overwritten in sidebar once llm_available() is resolved
live = False
provider_label = ""

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)

SAMPLES = [
    ("Trigger extraction", "#F43F5E", "Chronological trigger extraction",
     "Find the rare initiator beneath a flood of downstream 503 symptoms.",
     "What caused the 503 errors for TENANT-X around 16:10?"),
    ("Noise demux", "#FB923C", "High-volume noise demultiplexing",
     "Surface a quiet anomaly buried under another tenant's volumetric flood.",
     "Identify any system failures impacting TENANT-Z during the authentication volume spike."),
    ("Triage", "#22D3EE", "Unscoped triage",
     "No tenant named — the engine surfaces the most severe active incident.",
     "Which tenant is currently experiencing an outage?"),
    ("Health check", "#34D399", "Healthy-tenant check",
     "Confirms a tenant is clean without inventing a failure.",
     "Are there any failures affecting TENANT-A?"),
]

st.session_state.setdefault("q", SAMPLES[0][4])
st.session_state.setdefault("view", "home")
st.session_state.setdefault("history", [])
st.session_state.setdefault("result_cache", {})  # query_key → {res, stats}
st.session_state.setdefault("upload_status", [])  # list of upload confirmation messages


# ─────────────────────────────── engine cache ───────────────────────────────
@st.cache_resource(show_spinner=False)
def _engine_for(files_key: tuple, with_vectors: bool):
    """Build + cache the engine once per (corpus, vectors) for the whole session.
    Uses st.cache_resource (not cache_data) — the engine holds a DB connection."""
    return build_engine(list(files_key), with_vectors=with_vectors)


def _run_investigation(query: str, chosen: list, with_vectors: bool, use_llm: bool):
    """Run query via the engine. Results are stored in session-state (not pickle-cached)
    to avoid the UnserializableReturnValueError — RCAResult holds a DuckDB connection."""
    cache_key = f"{query}|{','.join(chosen)}|{with_vectors}|{use_llm}|{settings.provider}"
    if cache_key in st.session_state["result_cache"]:
        return st.session_state["result_cache"][cache_key]

    engine, stats = _engine_for(tuple(chosen), with_vectors)
    res = engine.investigate(query, use_llm=use_llm)

    entry = {"res": res, "stats": stats}
    st.session_state["result_cache"][cache_key] = entry
    return entry


def _run_and_store(query: str, chosen: list, with_vectors: bool, use_llm: bool):
    entry = _run_investigation(query, chosen, with_vectors, use_llm)
    res, stats = entry["res"], entry["stats"]
    st.session_state["result"] = {"q": query, "res": res, "stats": stats}

    ts = datetime.datetime.now().strftime("%H:%M")
    tenant = res.chain.tenant_id or "?"
    answer_short = re.sub(r"^\s*\**\s*", "", res.answer)[:80]
    hist_entry = {"q": query, "tenant": tenant, "answer": answer_short,
                  "ts": ts, "res": res, "stats": stats}
    hist = st.session_state["history"]
    if not hist or hist[0]["q"] != query:
        hist.insert(0, hist_entry)
        if len(hist) > 20:
            hist.pop()


# ─────────────────────────────── navigation callbacks ───────────────────────
def _goto(query: str):
    st.session_state["q"] = query
    st.session_state["view"] = "result"
    st.session_state["pending"] = query


def _investigate():
    st.session_state["view"] = "result"
    st.session_state["pending"] = st.session_state["q"]


def _home():
    st.session_state["view"] = "home"
    st.session_state.pop("result", None)
    st.session_state.pop("pending", None)


def _restore(idx: int):
    entry = st.session_state["history"][idx]
    st.session_state["q"] = entry["q"]
    st.session_state["view"] = "result"
    st.session_state["result"] = {"q": entry["q"], "res": entry["res"],
                                   "stats": entry["stats"]}


def _delete_hist(idx: int):
    st.session_state["history"].pop(idx)


# ─────────────────────────────── sidebar ────────────────────────────────────
with st.sidebar:
    st.markdown(ui.brand_html(), unsafe_allow_html=True)

    # ── Corpus ──────────────────────────────────────────────────────────────
    available = sorted(
        [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith(".log")]
    )
    st.markdown('<div class="side-label">Corpus</div>', unsafe_allow_html=True)
    chosen = st.multiselect("Log files", available, default=available,
                            format_func=os.path.basename, label_visibility="collapsed")

    # ── Upload log files ─────────────────────────────────────────────────────
    st.markdown('<div class="side-label">Upload logs</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Drop .log files", type=["log", "txt"],
        accept_multiple_files=True, label_visibility="collapsed",
        help="Upload any log file — the engine auto-detects the format and ingests immediately.")

    if uploaded:
        newly_added = []
        for uf in uploaded:
            dest = os.path.join(DATA_DIR, uf.name)
            if not os.path.exists(dest):
                data = uf.read()
                line_count = data.count(b"\n")
                with open(dest, "wb") as fh:
                    fh.write(data)
                newly_added.append((uf.name, line_count))

        if newly_added:
            # Invalidate caches so the new file auto-loads on next investigate
            st.session_state.pop("warm_key", None)
            _engine_for.clear()
            st.session_state["result_cache"].clear()
            # Build a friendly upload confirmation message
            msgs = [f"✓ **{n}** — {l:,} lines ready" for n, l in newly_added]
            st.session_state["upload_status"] = msgs
            st.rerun()

    # Show upload confirmations (persist until next upload or page clear)
    for msg in st.session_state.get("upload_status", []):
        st.markdown(
            f'<div class="status-row" style="background:rgba(52,211,153,.10);'
            f'border:1px solid rgba(52,211,153,.3);margin-top:6px">'
            f'<span class="dot live"></span><span style="color:#6EE7B7;font-size:.8rem">'
            f'{msg}</span></div>', unsafe_allow_html=True)

    # ── AI Engine ────────────────────────────────────────────────────────────
    st.markdown('<div class="side-label">AI Engine</div>', unsafe_allow_html=True)
    live = llm_available()

    if live:
        # Gemini key configured — default ON, show provider name
        use_llm = st.checkbox("Use Gemini synthesis", value=True,
                              help="Adds a Gemini-written cited narrative. Turn off for "
                                   "instant deterministic-only answers (still 100% accurate).")
        provider_label = settings.gemini_model if hasattr(settings, "gemini_model") else settings.provider
        if use_llm:
            st.markdown(
                f'<div class="status-row"><span class="dot live"></span>'
                f'<span style="font-size:.82rem">Connected &middot; <b>{ui.esc(provider_label)}</b></span></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="status-row" style="border-color:rgba(34,211,238,.3)">'
                '<span class="dot" style="background:#22D3EE;box-shadow:0 0 0 4px rgba(34,211,238,.16)"></span>'
                '<span style="font-size:.82rem;color:#67E8F9">Deterministic only &middot; instant</span></div>',
                unsafe_allow_html=True)
    else:
        use_llm = False
        st.markdown(
            '<div class="status-row"><span class="dot off"></span>'
            '<span style="font-size:.82rem;color:var(--muted)">No API key &middot; deterministic mode</span></div>',
            unsafe_allow_html=True)
        st.caption("Set GOOGLE_API_KEY in .env to enable AI synthesis.")

    use_vectors = st.checkbox("Semantic index", value=False,
                              help="Optional vector layer — not needed for the sample scenarios.")

    # Flag if the engine needs warming — actual warming happens in the main area
    # so the sidebar stays visible and the main area shows a proper loading screen.
    warm_key = (tuple(chosen), use_vectors)
    needs_warm = bool(chosen and st.session_state.get("warm_key") != warm_key)

    # ── Navigation (result view only) ────────────────────────────────────────
    if st.session_state["view"] == "result":
        st.markdown('<div class="side-label">Navigation</div>', unsafe_allow_html=True)
        st.button("← Overview", key="nav_back_side", on_click=_home,
                  use_container_width=True)

    # ── History ──────────────────────────────────────────────────────────────
    hist = st.session_state["history"]
    if hist:
        st.markdown('<div class="side-label">History</div>', unsafe_allow_html=True)
        for idx, entry in enumerate(hist):
            st.markdown(
                ui.hist_item_html(entry["q"], entry["tenant"],
                                  entry["answer"], entry["ts"]),
                unsafe_allow_html=True)
            hc1, hc2 = st.columns([0.78, 0.22])
            hc1.button("View", key=f"hv_{idx}", on_click=_restore, args=(idx,),
                       use_container_width=True)
            hc2.button("✕", key=f"hd_{idx}", on_click=_delete_hist, args=(idx,),
                       use_container_width=True, help="Remove from history")

    st.markdown(
        '<div class="side-foot">Deterministic-first RCA &middot; tenant isolation, '
        'template rarity and causal ordering precede every AI call.<br><br>'
        'v1.0 &middot; Confidential</div>', unsafe_allow_html=True)


# ─────────────────────────────── result rendering ───────────────────────────
def render_result(res, stats):
    chain = res.chain
    has_cause = chain.trigger is not None

    if chain.chronology_verified:
        chrono = ("verified", "#34D399")
    elif has_cause:
        chrono = ("unverified", "#F59E0B")
    else:
        chrono = ("n / a", "#64748B")

    st.markdown(ui.metrics_html(stats.events, stats.distinct_templates,
                                stats.ingest_seconds, chrono[0], chrono[1]),
                unsafe_allow_html=True)

    answer = re.sub(r"^\s*(\([a-z]\)\s*)?\**\s*(answer)\s*:?\s*\**\s*", "",
                    res.answer, flags=re.IGNORECASE).strip() or res.answer
    st.markdown(ui.verdict_html(answer, chain.chronology_verified,
                                res.citations_verified, res.llm_used, has_cause=has_cause),
                unsafe_allow_html=True)

    for w in res.warnings:
        st.markdown(ui.note_html(w), unsafe_allow_html=True)

    items = ""
    for p in chain.precursors:
        items += ui.timeline_item("precursor", str(p["first_seen"]),
            f"x{p['count']} · event {p['example_event_id']}", ui.esc(p["template_text"]))
    if chain.trigger:
        t = chain.trigger
        fc = getattr(chain, "trigger_class", "")
        fc_label = f" [{fc}]" if fc and fc != "UNKNOWN" else ""
        items += ui.timeline_item("trigger", str(t.ts),
            f"event {t.event_id} · {t.component}{fc_label}", ui.esc(t.message),
            trace=t.stack_trace or "")
    for tr in chain.transitions:
        items += ui.timeline_item("transition", str(tr.ts),
            f"event {tr.event_id} · {tr.component}", ui.esc(tr.message))
    for s in chain.symptoms:
        items += ui.timeline_item("symptom", str(s["first_seen"]),
            f"x{s['count']} · event {s['example_event_id']}", ui.esc(s["template_text"]))

    if items:
        st.markdown(ui.section_html("Causal chain", "trigger precedes symptoms"),
                    unsafe_allow_html=True)
        st.markdown(f'<div class="tl rise">{items}</div>', unsafe_allow_html=True)

    if has_cause:
        notes = [n for n in chain.notes if not n.startswith("Chronology verified")]
        if notes:
            st.markdown(ui.section_html("Exclusions & notes"), unsafe_allow_html=True)
            for n in notes:
                st.markdown(ui.note_html(n), unsafe_allow_html=True)
    elif chain.notes:
        # Show notes even when there's no trigger (e.g. unknown tenant, healthy tenant)
        st.markdown(ui.section_html("Analysis notes"), unsafe_allow_html=True)
        for n in chain.notes:
            st.markdown(ui.note_html(n), unsafe_allow_html=True)

    if res.evidence:
        st.markdown(ui.section_html("Evidence", f"{len(res.evidence)} cited lines"),
                    unsafe_allow_html=True)
        for e in res.evidence:
            st.markdown(ui.evidence_html(e.level, e.citation(), e.component,
                                         e.message, e.stack_trace), unsafe_allow_html=True)

    if res.llm_used:
        st.markdown(ui.section_html("Analyst narrative", provider_label if live else ""),
                    unsafe_allow_html=True)
        st.markdown(res.narrative)


# ─────────────────────────────── HOME view ──────────────────────────────────
def view_home():
    st.markdown(ui.hero_html(), unsafe_allow_html=True)
    st.markdown(ui.section_html("How it works"), unsafe_allow_html=True)
    st.markdown(ui.overview_html(), unsafe_allow_html=True)

    st.markdown(ui.section_html("Try a scenario"), unsafe_allow_html=True)
    st.markdown('<div class="samples-intro">Pick a scenario to run it instantly, or '
                'write your own question below.</div>', unsafe_allow_html=True)
    for row in [SAMPLES[:2], SAMPLES[2:]]:
        cols = st.columns(2)
        for col, (tag, color, title, desc, q) in zip(cols, row):
            with col:
                st.markdown(ui.scard_html(tag, color, title, desc, q), unsafe_allow_html=True)
                st.button("Run scenario", key=f"s_{tag}", on_click=_goto, args=(q,),
                          use_container_width=True)

    st.markdown(ui.section_html("Ask your own"), unsafe_allow_html=True)
    st.text_input("query", key="q", label_visibility="collapsed",
                  placeholder="e.g. What caused the latency spike for TENANT-C?")
    st.button("Investigate", type="primary", on_click=_investigate)

    st.markdown(ui.section_html("Built with"), unsafe_allow_html=True)
    st.markdown(ui.tech_stack_html(), unsafe_allow_html=True)


# ─────────────────────────────── RESULT view ────────────────────────────────
def view_result(chosen, use_vectors, use_llm):
    # Compact topbar
    tc1, tc2 = st.columns([0.18, 0.82])
    with tc1:
        st.markdown('<div class="back-btn">', unsafe_allow_html=True)
        st.button("← Overview", key="nav_back_top", on_click=_home,
                  use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    with tc2:
        st.markdown('<div class="topbar"><span class="crumb">Overview&nbsp;/&nbsp;'
                    '<b>Investigation</b></span></div>', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Incident question</div>', unsafe_allow_html=True)
    st.text_input("query", key="q", label_visibility="collapsed")
    c1, _ = st.columns([0.26, 0.74])
    c1.button("Investigate", type="primary", on_click=_investigate, use_container_width=True)

    pending = st.session_state.pop("pending", None)
    if pending:
        if not chosen:
            st.markdown(ui.note_html(
                "No log files selected. Pick at least one in the Corpus section of the sidebar."),
                unsafe_allow_html=True)
        else:
            msg = "Analysing with Gemini…" if use_llm and live else "Investigating…"
            with st.spinner(msg):
                try:
                    _run_and_store(pending, chosen, use_vectors, use_llm)
                except Exception as e:
                    st.error(f"Investigation failed: {e}\n\nTry refreshing the page or "
                             f"removing the corpus and re-adding it.")
                    st.stop()

    stored = st.session_state.get("result")
    if stored:
        render_result(stored["res"], stored["stats"])
    elif not pending:
        st.markdown(
            '<div class="empty rise"><div class="ring"><div class="core"></div></div>'
            '<h3>Enter a question and press Investigate</h3>'
            '<p>The engine returns a cited root cause — not a wall of logs.</p></div>',
            unsafe_allow_html=True)


# ─────────────────────────────── corpus warm-up (main area) ─────────────────
# Warming happens here (not inside the sidebar block) so the sidebar stays
# visible and the main area shows an informative loading screen instead of
# being blank while the engine ingests the corpus.
if needs_warm:
    st.markdown(
        """
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;height:60vh;gap:1.4rem;text-align:center">
          <div style="font-size:2.6rem;animation:spin 1.1s linear infinite;
                      display:inline-block">⚙️</div>
          <div style="font-size:1.25rem;font-weight:600;color:#E8ECF6">
            Loading corpus…
          </div>
          <div style="font-size:.9rem;color:#64748B;max-width:340px">
            Ingesting log files, mining templates and building the structural index.
            This only happens once — queries will be instant afterwards.
          </div>
        </div>
        <style>
          @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        </style>
        """,
        unsafe_allow_html=True,
    )
    try:
        _engine_for(*warm_key)
        st.session_state["warm_key"] = warm_key
        st.session_state["upload_status"] = []
    except Exception as e:
        st.error(f"Failed to load corpus: {e}")
    st.rerun()

# ─────────────────────────────── router ─────────────────────────────────────
# st.empty() clears the previous view DOM instantly on navigation (no ghost content).
screen = st.empty()
with screen.container():
    if st.session_state["view"] == "home":
        view_home()
    else:
        view_result(chosen, use_vectors, use_llm)
