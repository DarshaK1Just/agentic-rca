"""RCA Engine — Root-level entry point for Streamlit Cloud.

This file allows Streamlit Cloud to run: streamlit run app

It imports and runs the actual webapp from src/rca/webapp.py
"""
import os
import sys

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Import and run the webapp
from rca import webapp  # noqa: F401
