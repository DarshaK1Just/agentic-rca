"""Deterministic ingestion contract — grammar, multi-line coalescing, template dedup."""
import os

from rca.ingest.normalize import ingest_file
from rca.store.schema import Level

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
PROD = os.path.join(DATA, "production_incident_01.log")


def test_full_parse_no_unparsed_lines():
    events = ingest_file(PROD)
    assert len(events) > 4900
    # The grammar is regular — nothing should fall back to RAW.
    assert sum(1 for e in events if e.level == Level.RAW) == 0


def test_multiline_stack_trace_is_coalesced():
    events = ingest_file(PROD)
    trigger = next(e for e in events if "ConnectionTimeoutException" in e.message)
    assert trigger.stack_trace is not None
    assert "getConnection" in trigger.stack_trace
    # The continuation lines must NOT have become their own events.
    assert not any(e.message.strip().startswith("at com.") for e in events)


def test_template_collapses_the_503_flood():
    events = ingest_file(PROD)
    err503 = [e for e in events if e.params.get("status") == "503"]
    assert len(err503) > 200                       # the flood exists
    assert len({e.template_id for e in err503}) == 1  # ...but is ONE template


def test_trigger_template_is_unique():
    events = ingest_file(PROD)
    from collections import Counter
    counts = Counter(e.template_id for e in events)
    trigger = next(e for e in events if "ConnectionTimeoutException" in e.message)
    assert counts[trigger.template_id] == 1        # rare ⇒ diagnostically salient
