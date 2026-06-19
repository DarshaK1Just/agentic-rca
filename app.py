"""Streamlit Cloud entry point — RCA Engine.

Three jobs, in order:
  1. Resolve project root and make src.rca importable.
  2. Sync Streamlit Cloud secrets → os.environ so pydantic Settings picks them up.
  3. exec() the Streamlit frontend (src/rca/webapp.py) in-process.

Local use: `streamlit run app.py`
Streamlit Cloud: connect this repo, set main file to app.py,
paste secrets from .streamlit/secrets.toml.example into the Secrets panel.
"""
import os
import sys
from pathlib import Path

import streamlit as st

# ── 1. Resolve project root and make src.* importable ────────────────────────
_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Relative paths in config must resolve to project root
os.chdir(_HERE)

# ── 2. Sync Streamlit Cloud secrets → os.environ ─────────────────────────────
# On Streamlit Cloud, secrets are in st.secrets (set via the dashboard).
# On local dev, st.secrets is empty and config loads .env directly.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k.upper(), _v)
except Exception:
    pass  # no secrets configured — local dev mode, .env file handles credentials

# ── 3. Run the Streamlit frontend in-process ──────────────────────────────────
# Override __file__ so path calculations inside webapp.py resolve correctly.
_webapp = _SRC / "rca" / "webapp.py"
_g = globals().copy()
_g["__file__"] = str(_webapp)
exec(_webapp.read_text(encoding="utf-8"), _g)  # noqa: S102
