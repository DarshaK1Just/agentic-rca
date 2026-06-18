"""RCA Engine — custom incident console (Streamlit).

Run:  streamlit run src/rca/webapp.py

Two views share a branded sidebar:
  • Overview (home) — what the engine does, how it works, sample scenarios, the stack,
    and a free-text box for any custom question.
  • Investigation (result) — an editable query bar plus metrics → verdict → causal
    timeline → evidence for the active question.

Results are cached in session state so widget interactions (expanding a stack trace,
editing the query) never silently re-spend an LLM call.
"""
from __future__ import annotations

import os
import re
import sys
import warnings

# Allow `streamlit run src/rca/webapp.py` without setting PYTHONPATH.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

warnings.filterwarnings("ignore")

import streamlit as st

from rca.agent.llm_provider import llm_available
from rca.config import settings
from rca.pipeline import build_engine
from rca import ui_theme as ui

st.set_page_config(page_title="RCA Engine — Log Intelligence Console", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

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


# ─────────────────────────────── helpers / navigation ───────────────────────
@st.cache_resource(show_spinner=False)
def _engine_for(files_key: tuple, with_vectors: bool):
    return build_engine(list(files_key), with_vectors=with_vectors)


def _goto(query: str):
    st.session_state["q"] = query
    st.session_state["view"] = "result"
    st.session_state["pending"] = query


def _investigate():
    st.session_state["view"] = "result"
    st.session_state["pending"] = st.session_state["q"]


def _home():
    st.session_state["view"] = "home"


def _run_and_store(query: str, chosen, use_vectors):
    engine, stats = _engine_for(tuple(chosen), use_vectors)
    res = engine.investigate(query)
    st.session_state["result"] = {"q": query, "res": res, "stats": stats}


# ─────────────────────────────── sidebar ────────────────────────────────────
with st.sidebar:
    st.markdown(ui.brand_html(), unsafe_allow_html=True)

    available = []
    if os.path.isdir(DATA_DIR):
        available = [os.path.join(DATA_DIR, f) for f in sorted(os.listdir(DATA_DIR))
                     if f.endswith(".log")]

    st.markdown('<div class="side-label">Corpus</div>', unsafe_allow_html=True)
    chosen = st.multiselect("Log files", available, default=available,
                            format_func=os.path.basename, label_visibility="collapsed")
    use_vectors = st.checkbox("Build semantic index", value=False,
                              help="Optional vector layer over the template catalogue. "
                                   "Both scenarios are solved without it.")

    st.markdown('<div class="side-label">Synthesis</div>', unsafe_allow_html=True)
    live = llm_available()
    st.markdown(ui.status_html(live, settings.provider), unsafe_allow_html=True)

    if st.session_state["view"] == "result":
        st.markdown('<div class="side-label">Navigation</div>', unsafe_allow_html=True)
        st.button("Back to overview", on_click=_home, use_container_width=True)

    st.markdown(
        '<div class="side-foot">Deterministic-first RCA &middot; tenant isolation, '
        'template rarity and chronological causal ordering precede any LLM call.<br><br>'
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
        items += ui.timeline_item("trigger", str(t.ts),
            f"event {t.event_id} · {t.component}", ui.esc(t.message), trace=t.stack_trace or "")
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

    if res.evidence:
        st.markdown(ui.section_html("Evidence", f"{len(res.evidence)} cited lines"),
                    unsafe_allow_html=True)
        for e in res.evidence:
            st.markdown(ui.evidence_html(e.level, e.citation(), e.component,
                                         e.message, e.stack_trace), unsafe_allow_html=True)

    if res.llm_used:
        st.markdown(ui.section_html("Analyst narrative", settings.provider),
                    unsafe_allow_html=True)
        st.markdown(res.narrative)


# ─────────────────────────────── HOME view ──────────────────────────────────
def view_home():
    st.markdown(ui.hero_html(), unsafe_allow_html=True)

    st.markdown(ui.section_html("How it works"), unsafe_allow_html=True)
    st.markdown(ui.overview_html(), unsafe_allow_html=True)

    st.markdown(ui.section_html("Try a scenario"), unsafe_allow_html=True)
    st.markdown('<div class="samples-intro">Pick a scenario to run it instantly, or write '
                'your own question below.</div>', unsafe_allow_html=True)
    rows = [SAMPLES[:2], SAMPLES[2:]]
    for row in rows:
        cols = st.columns(2)
        for col, (tag, color, title, desc, q) in zip(cols, row):
            with col:
                st.markdown(ui.scard_html(tag, color, title, desc, q), unsafe_allow_html=True)
                st.button("Run scenario", key=f"s_{tag}", on_click=_goto, args=(q,),
                          use_container_width=True)

    st.markdown(ui.section_html("Ask your own"), unsafe_allow_html=True)
    st.text_input("query", key="q", label_visibility="collapsed",
                  placeholder="e.g. What caused the latency spike for TENANT-C this afternoon?")
    st.button("Investigate", type="primary", on_click=_investigate)

    st.markdown(ui.section_html("Built with"), unsafe_allow_html=True)
    st.markdown(ui.tech_stack_html(), unsafe_allow_html=True)


# ─────────────────────────────── RESULT view ────────────────────────────────
def view_result(chosen, use_vectors):
    st.markdown('<div class="topbar"><span class="crumb">Overview&nbsp;/&nbsp;'
                '<b>Investigation</b></span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">Incident question</div>', unsafe_allow_html=True)
    st.text_input("query", key="q", label_visibility="collapsed")
    c1, c2 = st.columns([0.26, 0.74])
    c1.button("Investigate", type="primary", on_click=_investigate, use_container_width=True)

    pending = st.session_state.pop("pending", None)
    if pending:
        if not chosen:
            st.markdown(ui.note_html("Select at least one log file in the sidebar to begin."),
                        unsafe_allow_html=True)
        else:
            with st.spinner("Ingesting corpus and investigating…"):
                _run_and_store(pending, chosen, use_vectors)

    stored = st.session_state.get("result")
    if stored:
        render_result(stored["res"], stored["stats"])
    elif not pending:
        st.markdown(
            '<div class="empty rise"><div class="ring"><div class="core"></div></div>'
            '<h3>Enter a question and press Investigate</h3>'
            '<p>The engine returns a cited root cause — not a wall of logs.</p></div>',
            unsafe_allow_html=True)


# ─────────────────────────────── router ─────────────────────────────────────
if st.session_state["view"] == "home":
    view_home()
else:
    view_result(chosen, use_vectors)
