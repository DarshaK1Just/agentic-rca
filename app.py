"""Streamlit Cloud entry point — RCA Engine.

Four jobs, in order:
  1. Set page config FIRST (required by Streamlit).
  2. Sync Streamlit Cloud secrets → os.environ so pydantic Settings picks them up.
  3. Set up the path so src.rca modules are importable.
  4. exec() the Streamlit frontend (src/rca/webapp.py) in-process.

Local use: `streamlit run app.py`
Streamlit Cloud: connect this repo, set main file to app.py,
paste secrets from .env into the Secrets panel.
"""
import os
import sys
from pathlib import Path

import streamlit as st

# ── 1. Set page config FIRST (must be the very first Streamlit command) ──────
st.set_page_config(page_title="RCA Engine — Log Intelligence Console", layout="wide")

# ── 2. Resolve project root and make src.* importable ────────────────────────
_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Relative paths in config must resolve to project root
os.chdir(_HERE)

# ── 3. Sync Streamlit Cloud secrets → os.environ ─────────────────────────────
# On Streamlit Cloud, secrets are in st.secrets (set via the dashboard).
# On local dev, st.secrets is empty and config loads .env directly.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k.upper(), _v)
except Exception:
    pass  # no secrets configured — local dev mode, .env file handles credentials

# ── 4. Run the Streamlit frontend in-process ──────────────────────────────────
# Read webapp.py and remove its st.set_page_config call (we already did it above)
_webapp = _SRC / "rca" / "webapp.py"
_webapp_code = _webapp.read_text(encoding="utf-8")

# Remove the st.set_page_config line since we already set it
import re
_webapp_code = re.sub(
    r'st\.set_page_config\([^)]*\)\s*\n',
    '',
    _webapp_code,
    count=1
)

# Override __file__ in the exec namespace so path calculations inside webapp.py resolve correctly
_g = globals().copy()
_g["__file__"] = str(_webapp)
exec(_webapp_code, _g)  # noqa: S102
