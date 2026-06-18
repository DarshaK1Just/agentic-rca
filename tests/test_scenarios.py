"""The two System Validation Scenarios from the assignment, as executable assertions.

These are the real grade: they prove the engine isolates the low-frequency trigger
from a symptom flood (Scenario 1) and a quiet anomaly from a cross-tenant noise flood
(Scenario 2) — deterministically, with no LLM in the loop.
"""


# ── Scenario 1: Chronological Trigger Extraction ────────────────────────────────
def test_scenario1_isolates_connection_pool_trigger(prod_engine):
    engine, _ = prod_engine
    res = engine.investigate("What caused the 503 errors for TENANT-X around 16:10?")

    # The named root cause is the connection-pool timeout, NOT a 503 symptom.
    assert res.chain.trigger is not None
    assert "ConnectionTimeoutException" in res.chain.trigger.message
    assert res.chain.trigger.component == "com.service.db.DataSource"
    assert "503" not in res.answer  # the 503s are symptoms, never the answer

    # The circuit-breaker transition is captured between cause and symptoms.
    assert any("CLOSED -> OPEN" in t.message for t in res.chain.transitions)

    # The 237-line 503 flood is classified as a downstream SYMPTOM.
    # (Drain3 masks the numeric 503 → <NUM>; the descriptive text survives.)
    assert any(s["count"] > 200 and "Service Unavailable" in s["template_text"]
               for s in res.chain.symptoms)

    # Cause precedes effect — the verifiable causal invariant.
    assert res.chain.chronology_verified is True


def test_scenario1_trigger_line_is_citable(prod_engine):
    engine, _ = prod_engine
    res = engine.investigate("Why did TENANT-X start returning 503s?")
    cited_ids = {e.event_id for e in res.evidence}
    assert res.chain.trigger.event_id in cited_ids          # lineage holds
    assert res.chain.trigger.stack_trace is not None         # evidence includes trace


# ── Scenario 2: High-Volume Noise Demultiplexing ────────────────────────────────
def test_scenario2_isolates_quiet_tenantz_anomaly(auth_engine):
    engine, _ = auth_engine
    res = engine.investigate(
        "Identify any system failures impacting TENANT-Z during the authentication "
        "volume spike.")

    assert res.chain.tenant_id == "TENANT-Z"
    assert res.chain.trigger is not None
    assert "token validation" in res.chain.trigger.message.lower()
    assert res.chain.trigger.component == "com.auth.handler.TokenValidator"


def test_scenario2_excludes_tenant_y_flood(auth_engine):
    engine, _ = auth_engine
    res = engine.investigate("What failed for TENANT-Z?")

    # The 429 flood belongs to TENANT-Y and must never be attributed to TENANT-Z.
    assert "429" not in res.answer
    assert all(e.tenant_id == "TENANT-Z" for e in res.evidence)
    # ...and it is explicitly named as unrelated noise.
    assert any("noise" in n.lower() and "TENANT-Y" in n for n in res.chain.notes)
