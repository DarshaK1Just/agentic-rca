"""Shared fixtures. These tests run with NO LLM key — they exercise the deterministic
core that must be correct regardless of the model layer."""
import os

import pytest

from rca.pipeline import build_engine

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PROD_LOG = os.path.join(DATA, "production_incident_01.log")
AUTH_LOG = os.path.join(DATA, "auth_rate_limit_noise.log")


@pytest.fixture(scope="session")
def prod_engine():
    engine, stats = build_engine([PROD_LOG])
    engine.chat_model = None  # tests validate the deterministic core, not LLM prose
    return engine, stats


@pytest.fixture(scope="session")
def auth_engine():
    engine, stats = build_engine([AUTH_LOG])
    engine.chat_model = None
    return engine, stats
