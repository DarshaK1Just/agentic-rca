"""Custom UI theme for the RCA console — CSS + small HTML component builders.

Kept separate from webapp.py so the Streamlit page stays readable. Everything here
is presentation only; no business logic. Colour system:

  bg          #0A0E1A → #0D1426 (radial)     surface  #121A2E
  accent      indigo #6366F1 → cyan #22D3EE
  text        #E8ECF6           muted    #8A97B2
  severity    ERROR #F43F5E · WARN #F59E0B · INFO #34D399 · DEBUG #64748B
  phase       precursor #64748B · trigger #F43F5E · transition #F59E0B · symptom #FB923C
"""
from __future__ import annotations

import html

PHASE_COLORS = {
    "precursor": "#64748B",
    "trigger": "#F43F5E",
    "transition": "#F59E0B",
    "symptom": "#FB923C",
}
LEVEL_COLORS = {
    "ERROR": "#F43F5E", "FATAL": "#E11D48", "WARN": "#F59E0B",
    "INFO": "#34D399", "DEBUG": "#64748B", "TRACE": "#475569", "RAW": "#8A97B2",
}


def esc(x) -> str:
    return html.escape(str(x))


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --bg0:#0A0E1A; --bg1:#0D1426; --surface:#121A2E; --surface2:#162038;
  --border:rgba(255,255,255,.07); --border2:rgba(255,255,255,.12);
  --txt:#E8ECF6; --muted:#8A97B2; --faint:#5C6B86;
  --indigo:#6366F1; --cyan:#22D3EE; --violet:#A78BFA;
  --grad:linear-gradient(135deg,#6366F1 0%,#22D3EE 100%);
}

/* ---- base canvas ---- */
html, body, [class*="css"]{ font-family:'Inter',system-ui,sans-serif; }
.stApp{
  background:
    radial-gradient(1100px 600px at 12% -8%, rgba(99,102,241,.16), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(34,211,238,.10), transparent 55%),
    linear-gradient(180deg,#0A0E1A 0%,#0B1120 100%);
  color:var(--txt);
}
/* hide default chrome — ONLY the menu/footer/toolbar items, never the header
   element or its sidebar toggle buttons. The header stays fully functional;
   it's just a thin transparent bar at the top. */
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"]{ display:none !important; }
header[data-testid="stHeader"]{
  background:transparent !important;
  border-bottom:none !important;
  box-shadow:none !important;
}
/* ---- sidebar expand button (shown when sidebar is collapsed) ----
   Covers every test-id Streamlit has used across releases. We pin it to the
   top-left as a clearly visible, clickable chip so the sidebar can ALWAYS be
   re-opened after it's collapsed. */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stExpandSidebarButton"]{
  display:flex !important; visibility:visible !important;
  opacity:1 !important; pointer-events:auto !important;
  position:fixed !important; top:.7rem !important; left:.7rem !important;
  z-index:1000000 !important;
  background:var(--surface) !important;
  border:1px solid var(--border2) !important;
  border-radius:10px !important; padding:6px !important;
  box-shadow:0 6px 18px rgba(0,0,0,.4) !important;
}
[data-testid="collapsedControl"]:hover,
[data-testid="stSidebarCollapsedControl"]:hover,
[data-testid="stExpandSidebarButton"]:hover{
  border-color:var(--indigo) !important; background:var(--surface2) !important;
}
/* make the chevron icon clearly visible (was dark-on-dark) */
[data-testid="collapsedControl"] svg,
[data-testid="stSidebarCollapsedControl"] svg,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stSidebarCollapseButton"] svg{
  fill:#E8ECF6 !important; color:#E8ECF6 !important;
  width:22px !important; height:22px !important;
}
/* keep the in-sidebar collapse («) button visible & clickable too */
[data-testid="stSidebarCollapseButton"]{
  display:flex !important; visibility:visible !important;
  opacity:1 !important; pointer-events:auto !important;
}
.block-container{ padding-top:2.2rem; padding-bottom:4rem; max-width:1180px; }

/* ---- scrollbar ---- */
::-webkit-scrollbar{ width:10px; height:10px; }
::-webkit-scrollbar-thumb{ background:#243049; border-radius:8px; }
::-webkit-scrollbar-thumb:hover{ background:#30406180; }

/* ---- sidebar ---- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#0C1322 0%,#0A0F1C 100%);
  border-right:1px solid var(--border);
}
section[data-testid="stSidebar"] .block-container{ padding-top:1.4rem; }
.brand{ display:flex; align-items:center; gap:12px; margin:2px 0 22px; }
.brand-mark{
  width:42px;height:42px;border-radius:12px;background:var(--grad);
  display:flex;align-items:center;justify-content:center;flex:0 0 auto;
  box-shadow:0 8px 22px rgba(99,102,241,.45); position:relative;
}
.brand-mark::after{
  content:"";width:16px;height:16px;border:2.5px solid #0A0E1A;border-radius:50%;
  border-right-color:transparent; transform:rotate(-30deg);
}
.brand-title{ font-size:1.06rem;font-weight:800;letter-spacing:.2px;color:#fff;line-height:1; }
.brand-sub{ font-size:.7rem;font-weight:600;letter-spacing:.14em;color:var(--faint);
  text-transform:uppercase;margin-top:5px; }
.side-label{ font-size:.68rem;font-weight:700;letter-spacing:.16em;color:var(--faint);
  text-transform:uppercase;margin:20px 0 8px; }
.side-foot{ margin-top:26px;padding-top:14px;border-top:1px solid var(--border);
  font-size:.7rem;color:var(--faint);line-height:1.7; }
.status-row{ display:flex;align-items:center;gap:9px;padding:10px 12px;border-radius:11px;
  background:var(--surface);border:1px solid var(--border);font-size:.82rem;color:var(--txt); }
.dot{ width:9px;height:9px;border-radius:50%;flex:0 0 auto;
  box-shadow:0 0 0 4px rgba(52,211,153,.16);animation:pulse 2.2s infinite; }
.dot.live{ background:#34D399; }
.dot.off{ background:#64748B; box-shadow:0 0 0 4px rgba(100,116,139,.16); }
@keyframes pulse{ 0%,100%{opacity:1} 50%{opacity:.55} }

/* ---- hero ---- */
.hero{ animation:rise .55s cubic-bezier(.2,.7,.2,1) both; margin-bottom:6px; }
.eyebrow{ display:inline-flex;align-items:center;gap:8px;font-size:.72rem;font-weight:700;
  letter-spacing:.18em;text-transform:uppercase;color:var(--cyan);
  background:rgba(34,211,238,.08);border:1px solid rgba(34,211,238,.22);
  padding:6px 12px;border-radius:999px;margin-bottom:16px; }
.hero h1{ font-size:2.5rem;font-weight:800;line-height:1.08;margin:0 0 8px;letter-spacing:-.02em; }
.hero h1 .grad{ background:var(--grad);-webkit-background-clip:text;background-clip:text;
  -webkit-text-fill-color:transparent; }
.hero p{ color:var(--muted);font-size:1.02rem;max-width:760px;margin:0; }

/* ---- query / command bar ---- */
.sec-label{ font-size:.72rem;font-weight:700;letter-spacing:.16em;color:var(--faint);
  text-transform:uppercase;margin:26px 0 10px; }
[data-testid="stTextInput"] input{
  background:var(--surface) !important;border:1px solid var(--border2) !important;
  border-radius:14px !important;font-size:1.02rem !important;
  padding:16px 18px !important;height:auto !important;
  box-shadow:0 2px 18px rgba(0,0,0,.25) inset; transition:border-color .2s, box-shadow .2s; }
[data-testid="stTextInput"] input:focus{
  border-color:var(--indigo) !important;
  box-shadow:0 0 0 3px rgba(99,102,241,.25) !important; }
[data-testid="stTextInput"] input::placeholder{
  color:var(--faint) !important; -webkit-text-fill-color:var(--faint) !important; opacity:1; }
/* Force visible (light) text in EVERY input/textarea, all states. The default
   -webkit-text-fill-color can render typed text near-black-on-dark = invisible. */
input, textarea, .stTextInput input, [data-baseweb="input"] input,
[data-baseweb="select"] input, section[data-testid="stSidebar"] input{
  color:#E8ECF6 !important; -webkit-text-fill-color:#E8ECF6 !important;
  caret-color:#22D3EE !important; }

/* ---- buttons ---- */
.stButton>button{
  border-radius:12px;border:1px solid var(--border2);background:var(--surface);
  color:var(--txt);font-weight:600;font-size:.86rem;padding:9px 16px;
  transition:transform .15s, border-color .2s, background .2s; }
.stButton>button:hover{ transform:translateY(-1px);border-color:var(--indigo);
  background:var(--surface2);color:#fff; }
.stButton>button[kind="primary"]{
  background:var(--grad);border:none;color:#08101F;font-weight:800;letter-spacing:.02em;
  padding:13px 22px;font-size:.95rem;box-shadow:0 10px 26px rgba(99,102,241,.4); }
.stButton>button[kind="primary"]:hover{ transform:translateY(-2px);
  box-shadow:0 14px 34px rgba(99,102,241,.55);color:#000; }

/* ---- multiselect / checkbox tints ---- */
[data-testid="stMultiSelect"] [data-baseweb="tag"]{
  background:rgba(99,102,241,.18) !important;border:1px solid rgba(99,102,241,.4) !important; }
[data-baseweb="select"]>div{ background:var(--surface) !important;border-color:var(--border2) !important;
  border-radius:11px !important; }
/* dropdown popover — kill the bright white menu / "No results" box */
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="menu"], [data-baseweb="popover"] ul{
  background:#0F1830 !important;border:1px solid var(--border2) !important;
  border-radius:12px !important;box-shadow:0 18px 40px rgba(0,0,0,.5) !important;
  color:var(--txt) !important; }
[data-baseweb="popover"] li, [role="option"]{
  background:transparent !important;color:var(--txt) !important; }
[data-baseweb="popover"] li:hover, [role="option"]:hover{
  background:rgba(99,102,241,.18) !important; }
/* the empty-state ("No results") row baseweb renders */
[data-baseweb="popover"] [aria-disabled="true"],
[data-baseweb="menu"] div[role="option"][aria-disabled="true"]{
  color:var(--faint) !important;background:transparent !important;font-style:italic; }

/* ---- generic card + animations ---- */
.card{ background:var(--surface);border:1px solid var(--border);border-radius:16px;
  padding:18px 20px;box-shadow:0 10px 30px rgba(0,0,0,.28); }
.rise{ animation:rise .5s cubic-bezier(.2,.7,.2,1) both; }
@keyframes rise{ from{opacity:0;transform:translateY(14px)} to{opacity:1;transform:none} }

/* ---- metric strip ---- */
.metrics{ display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:8px 0 22px; }
.metric{ position:relative;overflow:hidden;background:var(--surface);
  border:1px solid var(--border);border-radius:16px;padding:16px 18px; }
.metric::before{ content:"";position:absolute;top:0;left:0;height:3px;width:100%;background:var(--grad); }
.metric .k{ font-size:.7rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--faint); }
.metric .v{ font-size:1.9rem;font-weight:800;margin-top:6px;line-height:1;color:#fff; }
.metric .u{ font-size:.74rem;color:var(--muted);margin-top:6px; }

/* ---- verdict ---- */
.verdict{ position:relative;background:linear-gradient(135deg,rgba(244,63,94,.10),rgba(99,102,241,.06));
  border:1px solid rgba(244,63,94,.32);border-left:4px solid #F43F5E;border-radius:16px;
  padding:20px 22px;margin-bottom:14px; }
.verdict .lab{ font-size:.7rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;
  color:#FB7185;margin-bottom:8px; }
.verdict .ans{ font-size:1.16rem;font-weight:600;color:#fff;line-height:1.5; }
.pills{ display:flex;flex-wrap:wrap;gap:9px;margin-top:14px; }
.pill{ display:inline-flex;align-items:center;gap:7px;font-size:.76rem;font-weight:600;
  padding:6px 12px;border-radius:999px;border:1px solid var(--border2);background:var(--surface); }
.pill .pd{ width:7px;height:7px;border-radius:50%; }
.pill.ok{ color:#6EE7B7;border-color:rgba(52,211,153,.35);background:rgba(52,211,153,.10); }
.pill.ok .pd{ background:#34D399; }
.pill.warn{ color:#FCD34D;border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.10); }
.pill.warn .pd{ background:#F59E0B; }
.pill.muted{ color:var(--muted); } .pill.muted .pd{ background:#64748B; }

/* ---- section heading ---- */
.h{ display:flex;align-items:center;gap:11px;margin:30px 0 14px; }
.h .bar{ width:4px;height:20px;border-radius:3px;background:var(--grad); }
.h .t{ font-size:1.18rem;font-weight:700;color:#fff;letter-spacing:-.01em; }
.h .c{ font-size:.74rem;color:var(--faint);font-weight:600; }

/* ---- timeline ---- */
.tl{ margin:4px 0 6px;padding-left:6px; }
.tl-item{ position:relative;padding:0 0 20px 30px;border-left:2px solid #1F2A44;margin-left:7px; }
.tl-item:last-child{ border-left-color:transparent; }
.tl-dot{ position:absolute;left:-9px;top:1px;width:16px;height:16px;border-radius:50%;
  border:3px solid #0B1120;box-shadow:0 0 0 3px rgba(255,255,255,.03); }
.tl-card{ background:var(--surface);border:1px solid var(--border);border-radius:13px;
  padding:13px 16px;transition:border-color .2s,transform .2s; }
.tl-card:hover{ border-color:var(--border2);transform:translateX(2px); }
.tl-top{ display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:5px; }
.badge{ font-size:.64rem;font-weight:800;letter-spacing:.1em;text-transform:uppercase;
  padding:3px 9px;border-radius:7px; }
.tl-time{ font-family:'JetBrains Mono',monospace;font-size:.74rem;color:var(--muted); }
.tl-meta{ font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--faint);
  margin-left:auto; }
.tl-msg{ color:var(--txt);font-size:.92rem;line-height:1.45; }
.tl-msg code{ font-family:'JetBrains Mono',monospace;font-size:.84rem;color:var(--cyan);
  background:rgba(34,211,238,.08);padding:1px 6px;border-radius:6px; }
.tl-trace{ font-family:'JetBrains Mono',monospace;font-size:.74rem;color:var(--muted);
  margin-top:8px;padding:9px 12px;background:#0C1322;border:1px solid var(--border);
  border-radius:9px;white-space:pre-wrap;line-height:1.55; }

/* ---- evidence ---- */
.ev{ background:var(--surface);border:1px solid var(--border);border-left:3px solid #64748B;
  border-radius:12px;padding:12px 15px;margin-bottom:10px; }
.ev-top{ display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px; }
.ev-lvl{ font-size:.64rem;font-weight:800;letter-spacing:.08em;padding:2px 8px;border-radius:6px; }
.ev-cite{ font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--faint); }
.ev-comp{ font-family:'JetBrains Mono',monospace;font-size:.72rem;color:var(--muted);margin-left:auto; }
.ev-msg{ font-family:'JetBrains Mono',monospace;font-size:.82rem;color:var(--txt);
  line-height:1.5;white-space:pre-wrap;word-break:break-word; }
.ev details{ margin-top:8px; }
.ev summary{ cursor:pointer;font-size:.74rem;color:var(--cyan);font-weight:600;outline:none; }
.ev pre{ font-family:'JetBrains Mono',monospace;font-size:.74rem;color:var(--muted);
  margin:8px 0 0;padding:9px 12px;background:#0C1322;border:1px solid var(--border);
  border-radius:9px;white-space:pre-wrap; }

/* ---- back-button (compact, inline-link style) ---- */
.back-btn button{ padding:5px 12px !important;font-size:.76rem !important;
  border-radius:9px !important;font-weight:600 !important;height:auto !important;
  line-height:1.3 !important;min-height:0 !important; }

/* ---- upload area ---- */
[data-testid="stFileUploader"]{ background:var(--surface);border:1px dashed var(--border2);
  border-radius:13px;padding:10px 12px; }
[data-testid="stFileUploader"] label{ color:var(--muted) !important;font-size:.8rem; }
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]{
  background:transparent !important;border:none !important; }
[data-testid="stFileUploaderDropzoneInstructions"]{ color:var(--faint) !important; }

/* ---- history items ---- */
.hist-item{ display:flex;align-items:flex-start;justify-content:space-between;gap:8px;
  padding:9px 11px;background:var(--surface);border:1px solid var(--border);
  border-radius:11px;margin-bottom:7px;cursor:pointer;transition:border-color .18s; }
.hist-item:hover{ border-color:var(--border2); }
.hist-q{ font-size:.78rem;color:var(--txt);font-weight:500;line-height:1.4;
  flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
.hist-meta{ font-size:.66rem;color:var(--faint);margin-top:3px; }
.hist-del{ font-size:.72rem;color:var(--faint);cursor:pointer;flex:0 0 auto;padding:2px 5px;
  border-radius:5px;border:1px solid transparent; }
.hist-del:hover{ color:#F43F5E;border-color:rgba(244,63,94,.3);background:rgba(244,63,94,.08); }

/* ---- note / exclusion callout ---- */
.note{ display:flex;gap:11px;background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.25);
  border-radius:12px;padding:12px 15px;margin:8px 0;color:#FCD9A6;font-size:.86rem;line-height:1.5; }
.note .ni{ color:#F59E0B;font-weight:800;flex:0 0 auto; }

/* ---- empty state ---- */
.empty{ text-align:center;padding:54px 20px;color:var(--muted); }
.empty .ring{ width:74px;height:74px;border-radius:50%;margin:0 auto 18px;
  border:2px dashed #2A375492;display:flex;align-items:center;justify-content:center; }
.empty .ring .core{ width:30px;height:30px;border-radius:9px;background:var(--grad);opacity:.85;
  animation:float 3s ease-in-out infinite; }
@keyframes float{ 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
.empty h3{ color:var(--txt);font-weight:700;margin:0 0 6px;font-size:1.05rem; }

/* ---- overview: how it works ---- */
.over{ display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:6px 0 8px; }
.step{ background:var(--surface);border:1px solid var(--border);border-radius:16px;
  padding:18px;position:relative;overflow:hidden; }
.step .n{ font-family:'JetBrains Mono',monospace;font-size:.8rem;font-weight:700;
  color:var(--cyan);background:rgba(34,211,238,.08);border:1px solid rgba(34,211,238,.22);
  width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
  margin-bottom:12px; }
.step h4{ margin:0 0 6px;font-size:1rem;font-weight:700;color:#fff; }
.step p{ margin:0;color:var(--muted);font-size:.86rem;line-height:1.55; }

/* ---- sample prompt cards (the clickable buttons live just under each) ---- */
.samples-intro{ color:var(--muted);font-size:.9rem;margin:2px 0 12px; }
.scard{ background:linear-gradient(160deg,var(--surface2),var(--surface));
  border:1px solid var(--border);border-radius:15px;padding:16px 17px 12px;
  height:100%;transition:border-color .2s,transform .2s; }
.scard:hover{ border-color:var(--border2);transform:translateY(-2px); }
.scard .tag{ display:inline-block;font-size:.62rem;font-weight:800;letter-spacing:.1em;
  text-transform:uppercase;padding:3px 9px;border-radius:7px;margin-bottom:10px; }
.scard h4{ margin:0 0 6px;font-size:.98rem;font-weight:700;color:#fff;line-height:1.3; }
.scard p{ margin:0 0 4px;color:var(--muted);font-size:.83rem;line-height:1.5; }
.scard .q{ display:block;margin-top:9px;font-family:'JetBrains Mono',monospace;
  font-size:.74rem;color:var(--cyan);background:rgba(34,211,238,.06);
  border:1px solid rgba(34,211,238,.16);border-radius:8px;padding:7px 10px;line-height:1.45; }

/* ---- tech stack badges ---- */
.stack{ display:flex;flex-wrap:wrap;gap:9px;margin-top:6px; }
.tech{ display:inline-flex;align-items:center;gap:8px;font-size:.8rem;font-weight:600;
  color:var(--txt);background:var(--surface);border:1px solid var(--border);
  padding:8px 13px;border-radius:11px; }
.tech .td{ width:8px;height:8px;border-radius:50%;background:var(--grad); }
.tech small{ color:var(--faint);font-weight:500; }

/* ---- result view top bar ---- */
.topbar{ display:flex;align-items:center;gap:10px;margin:2px 0 6px; }
.crumb{ font-size:.78rem;color:var(--faint);font-weight:600; }
.crumb b{ color:var(--cyan); }

/* ---- all-clear verdict variant ---- */
.verdict.clear{ background:linear-gradient(135deg,rgba(52,211,153,.10),rgba(34,211,238,.05));
  border:1px solid rgba(52,211,153,.32);border-left:4px solid #34D399; }
.verdict.clear .lab{ color:#6EE7B7; }
</style>
"""


def brand_html() -> str:
    return (
        '<div class="brand">'
        '<div class="brand-mark"></div>'
        '<div><div class="brand-title">RCA Engine</div>'
        '<div class="brand-sub">Log Intelligence Console</div></div>'
        '</div>'
    )


def hero_html() -> str:
    return (
        '<div class="hero">'
        '<span class="eyebrow">Agentic Diagnostics</span>'
        '<h1>Root&nbsp;Cause&nbsp;Analysis for <span class="grad">multi-tenant logs</span></h1>'
        '<p>Ask in plain English. The engine isolates the low-frequency trigger from the '
        'symptom flood, demultiplexes cross-tenant noise, and returns a cited, '
        'causally-ordered explanation — every claim traceable to a log line.</p>'
        '</div>'
    )


def status_html(live: bool, provider: str, ai_on: bool) -> str:
    if ai_on and live:
        return (f'<div class="status-row"><span class="dot live"></span>'
                f'LLM synthesis &middot; <b>{esc(provider)}</b></div>')
    if live:  # key configured, but AI narrative toggled off → fast deterministic
        return ('<div class="status-row"><span class="dot" style="background:#22D3EE;'
                'box-shadow:0 0 0 4px rgba(34,211,238,.16)"></span>'
                'Fast mode &middot; AI narrative off</div>')
    return ('<div class="status-row"><span class="dot off"></span>'
            'Deterministic mode &middot; no LLM key</div>')


def metrics_html(events: int, templates: int, ingest_s: float,
                 chrono_label: str, chrono_color: str) -> str:
    cards = [
        ("Events ingested", f"{events:,}", "log lines"),
        ("Templates", f"{templates}", "distinct patterns"),
        ("Ingest time", f"{ingest_s:.2f}", "seconds, single pass"),
    ]
    h = '<div class="metrics rise">'
    for k, v, u in cards:
        h += f'<div class="metric"><div class="k">{k}</div><div class="v">{v}</div><div class="u">{u}</div></div>'
    h += (f'<div class="metric"><div class="k">Causal chronology</div>'
          f'<div class="v" style="color:{chrono_color}">{esc(chrono_label)}</div>'
          f'<div class="u">trigger precedes symptoms</div></div>')
    return h + '</div>'


def section_html(title: str, count: str = "") -> str:
    c = f'<span class="c">{esc(count)}</span>' if count else ""
    return f'<div class="h"><span class="bar"></span><span class="t">{esc(title)}</span>{c}</div>'


def verdict_html(answer: str, verified: bool, citations_ok: bool, llm_used: bool,
                 has_cause: bool = True) -> str:
    if not has_cause:
        # No incident for this query (healthy / unknown tenant) — neutral, not alarming.
        pill = ('ok' if llm_used else 'muted',
                'LLM synthesis' if llm_used else 'Deterministic')
        ph = f'<span class="pill {pill[0]}"><span class="pd"></span>{esc(pill[1])}</span>'
        return ('<div class="verdict clear rise"><div class="lab">Result</div>'
                f'<div class="ans">{esc(answer)}</div>'
                f'<div class="pills">{ph}</div></div>')
    pills = [
        ('ok' if verified else 'warn',
         'Chronology verified' if verified else 'Chronology unverified'),
        ('ok' if citations_ok else 'warn',
         'Citations verified' if citations_ok else 'Citations unverified'),
        ('ok' if llm_used else 'muted',
         'LLM synthesis' if llm_used else 'Deterministic narrative'),
    ]
    ph = "".join(f'<span class="pill {c}"><span class="pd"></span>{esc(t)}</span>' for c, t in pills)
    return ('<div class="verdict rise"><div class="lab">Root cause</div>'
            f'<div class="ans">{esc(answer)}</div>'
            f'<div class="pills">{ph}</div></div>')


def _phase_badge(phase: str) -> str:
    color = PHASE_COLORS.get(phase, "#64748B")
    label = {"precursor": "Precursor", "trigger": "Root trigger",
             "transition": "State change", "symptom": "Symptom"}.get(phase, phase)
    return (color, f'<span class="badge" style="background:{color}22;color:{color};'
                   f'border:1px solid {color}55">{label}</span>')


def timeline_item(phase: str, time: str, meta: str, message_html: str, trace: str = "") -> str:
    color, badge = _phase_badge(phase)
    meta_h = f'<span class="tl-meta">{esc(meta)}</span>' if meta else ""
    trace_h = f'<div class="tl-trace">{esc(trace)}</div>' if trace else ""
    return (
        '<div class="tl-item">'
        f'<span class="tl-dot" style="background:{color}"></span>'
        '<div class="tl-card">'
        f'<div class="tl-top">{badge}<span class="tl-time">{esc(time)}</span>{meta_h}</div>'
        f'<div class="tl-msg">{message_html}</div>{trace_h}'
        '</div></div>'
    )


def evidence_html(level: str, citation: str, component: str, message: str, trace: str | None) -> str:
    color = LEVEL_COLORS.get(level, "#8A97B2")
    trace_h = ""
    if trace:
        trace_h = (f'<details><summary>stack trace</summary><pre>{esc(trace)}</pre></details>')
    return (
        f'<div class="ev" style="border-left-color:{color}">'
        '<div class="ev-top">'
        f'<span class="ev-lvl" style="background:{color}22;color:{color}">{esc(level)}</span>'
        f'<span class="ev-cite">{esc(citation)}</span>'
        f'<span class="ev-comp">{esc(component)}</span></div>'
        f'<div class="ev-msg">{esc(message)}</div>{trace_h}'
        '</div>'
    )


def hist_item_html(query: str, tenant: str, outcome: str, ts: str) -> str:
    """Sidebar history card — just the display markup; the Streamlit buttons sit below."""
    color = "#F43F5E" if "root cause" in outcome.lower() else \
            "#34D399" if "no failure" in outcome.lower() or "no warn" in outcome.lower() else \
            "#64748B"
    dot = f'<span style="display:inline-block;width:7px;height:7px;border-radius:50%;' \
          f'background:{color};margin-right:6px;vertical-align:middle"></span>'
    q_short = query if len(query) <= 52 else query[:49] + "…"
    return (
        f'<div class="hist-item">'
        f'<div><div class="hist-q">{dot}{esc(q_short)}</div>'
        f'<div class="hist-meta">{esc(tenant or "?")} &middot; {esc(ts)}</div></div>'
        f'</div>'
    )


def note_html(text: str) -> str:
    return f'<div class="note"><span class="ni">!</span><span>{esc(text)}</span></div>'


# ── overview / home components ───────────────────────────────────────────────
def overview_html() -> str:
    steps = [
        ("1", "Ingest &amp; isolate",
         "Heterogeneous log lines are parsed deterministically, mined into templates, "
         "and partitioned by tenant — one tenant&rsquo;s flood can never mask another&rsquo;s."),
        ("2", "Rank &amp; order",
         "Rare, high-severity events are ranked above repetitive symptoms, then ordered in "
         "time so the trigger is separated from its downstream effects."),
        ("3", "Cite &amp; synthesise",
         "An agent assembles a small evidence set and writes a causal explanation — every "
         "claim traceable to a log line, every citation verified."),
    ]
    cells = "".join(
        f'<div class="step"><div class="n">{n}</div><h4>{t}</h4><p>{p}</p></div>'
        for n, t, p in steps)
    return f'<div class="over rise">{cells}</div>'


def scard_html(tag: str, color: str, title: str, desc: str, query: str) -> str:
    return (
        f'<div class="scard"><span class="tag" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55">{esc(tag)}</span>'
        f'<h4>{esc(title)}</h4><p>{esc(desc)}</p>'
        f'<span class="q">{esc(query)}</span></div>'
    )


def tech_stack_html() -> str:
    items = [
        ("Drain3", "template mining"), ("DuckDB", "structural store"),
        ("Rarity index", "inverse frequency"), ("ChromaDB", "semantic layer"),
        ("LangGraph", "agent loop"), ("Gemini 2.5 Flash", "synthesis, BYOK"),
        ("Pydantic", "typed schema"), ("Streamlit", "console"),
    ]
    chips = "".join(
        f'<span class="tech"><span class="td"></span>{esc(n)} <small>{esc(d)}</small></span>'
        for n, d in items)
    return f'<div class="stack rise">{chips}</div>'
