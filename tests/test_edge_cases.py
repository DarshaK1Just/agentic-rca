"""Edge cases a reviewer is likely to throw at the engine — all on the deterministic
path (no LLM key). These guard the 'don't mislead' invariants."""
import os

import pytest

from rca.pipeline import build_engine

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PROD = os.path.join(DATA, "production_incident_01.log")
AUTH = os.path.join(DATA, "auth_rate_limit_noise.log")


@pytest.fixture(scope="session")
def both_engine():
    engine, _ = build_engine([PROD, AUTH])
    engine.chat_model = None  # deterministic-core tests
    return engine


def test_healthy_tenant_reports_no_failures_without_pivoting(both_engine):
    """A healthy, explicitly-named tenant must NOT be answered with another tenant's
    incident. This is the most important 'do no harm' guarantee."""
    res = both_engine.investigate("Are there any failures affecting TENANT-A?")
    assert res.chain.trigger is None
    assert "ConnectionTimeoutException" not in res.answer  # no leak from TENANT-X
    assert "no" in res.answer.lower() and "failure" in res.answer.lower() \
        or "no warn/error/fatal" in res.answer.lower()


def test_unknown_tenant_is_reported_not_substituted(both_engine):
    res = both_engine.investigate("What is happening with TENANT-Q?")
    assert res.chain.trigger is None
    assert "TENANT-Q" in res.answer
    assert "no log data" in res.answer.lower()


def test_no_tenant_surfaces_most_severe_incident(both_engine):
    res = both_engine.investigate("Which tenant is currently experiencing an outage?")
    assert res.chain.trigger is not None
    assert res.chain.tenant_id in ("TENANT-X", "TENANT-Z")


def test_garbage_query_degrades_gracefully(both_engine):
    res = both_engine.investigate("hello there")
    assert res.answer  # never throws; returns something sensible


def test_lowercase_tenant_reference_resolves(both_engine):
    res = both_engine.investigate("what caused the failures for tenant-x?")
    assert res.chain.tenant_id == "TENANT-X"
    assert "ConnectionTimeoutException" in res.chain.trigger.message


def test_both_scenarios_still_pass_with_two_files_loaded(both_engine):
    """Loading both corpora together must not cross-contaminate tenant analysis."""
    r1 = both_engine.investigate("What caused the 503 errors for TENANT-X?")
    assert "ConnectionTimeoutException" in r1.chain.trigger.message
    r2 = both_engine.investigate("Any failures impacting TENANT-Z?")
    assert "token validation" in r2.chain.trigger.message.lower()
    assert all(e.tenant_id == "TENANT-Z" for e in r2.evidence)
