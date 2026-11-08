"""The generated blocks of the reference docs match the code (like `npm run tokens:check`).

If a block is out of date, run: poetry run python scripts/docs/generate.py
"""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from core.settings import Settings
from evidence.record import decision_event
from gateway.reasons import all_reasons
from ports import EVENT_CATALOGUE, DecisionEntry
from tests.gateway_helpers import make_ctx
from tests.harness import ROOT

pytestmark = pytest.mark.unit


def _load_generator():
    spec = importlib.util.spec_from_file_location("docs_generate", ROOT / "scripts" / "docs" / "generate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def test_every_generated_block_is_up_to_date():
    stale = [str(p.relative_to(ROOT)) for p in gen.stale()]
    assert not stale, f"out of date: {stale}. Run: poetry run python scripts/docs/generate.py"


def test_the_check_flag_fails_on_a_stale_block_and_passes_when_current(tmp_path, monkeypatch):
    doc = tmp_path / "configuration.md"
    doc.write_text(f"intro\n{gen._begin('settings')}\nold text\n{gen._end('settings')}\noutro\n")
    monkeypatch.setattr(gen, "blocks", lambda: {doc: {"settings": "new text"}})
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.main(["--check"]) == 1
    assert doc.read_text().count("old text") == 1  # --check never writes
    assert gen.main([]) == 0
    assert doc.read_text() == f"intro\n{gen._begin('settings')}\nnew text\n{gen._end('settings')}\noutro\n"
    assert gen.main(["--check"]) == 0


def test_a_block_with_missing_markers_is_an_error():
    with pytest.raises(ValueError):
        gen.replace_block("no markers here", "settings", "x")


def test_every_setting_has_a_description_and_is_in_the_configuration_table():
    table = Path(gen.CONFIGURATION).read_text()
    for name, info in Settings.model_fields.items():
        assert info.description, f"{name} has no Field(description=...)"
        assert f"| `{name.upper()}` |" in table, f"{name} is missing from docs/configuration.md"


def test_every_secret_value_is_marked_secret():
    for name, info in Settings.model_fields.items():
        if info.annotation is not None and "SecretStr" in str(info.annotation):
            assert gen.is_secret(info), f"{name} holds a SecretStr but is not marked secret"
    for name in ("database_url", "migration_database_url", "redis_url", "jwt_secret", "azure_oai_key", "groq_api_key",
                 "s3_access_key_id", "s3_secret_access_key", "kafka_sasl_password", "receipt_signing_key"):
        assert gen.is_secret(Settings.model_fields[name]), name
    assert SecretStr  # imported for the annotation check above


def test_no_setting_falls_outside_a_group():
    assert "### Other" not in gen.settings_block()


def test_every_reason_code_is_in_the_api_readme():
    text = (ROOT / "docs" / "api" / "README.md").read_text()
    for reason in all_reasons():
        assert f"| `{reason.code}` |" in text


def test_the_event_catalogue_lists_the_data_fields_of_the_real_events():
    from workers.handlers.ingest import completed_event
    from workers.handlers.purge import purge_event

    by_type = {info.type: info for info in EVENT_CATALOGUE}
    ctx = make_ctx()
    decision = decision_event(DecisionEntry(
        ctx.principal.tenant_id, ctx.principal.id, ctx.request_id, ctx.trace_id, "kb.read", "legal", "allow",
        "allow", "allowed", None, None, None, {},
    ), uuid4())
    job = _job({"document_id": "d", "namespace": "n", "content_hash": "h"})
    events = [decision, completed_event(job, "done", 1), purge_event(job, 1, 2, "h", 90)]
    assert {e.type for e in events} == set(by_type)
    for event in events:
        info = by_type[event.type]
        assert tuple(event.data) == info.data_fields, event.type
        assert event.source == info.source, event.type


def _job(payload):
    from datetime import datetime, timezone

    from core.database.jobs import JobRow

    now = datetime.now(timezone.utc)
    return JobRow(
        id=uuid4(), tenant_id=uuid4(), kind="ingest", status="running", payload=payload, idempotency_key=None, attempts=1,
        max_attempts=5, run_after=now, lease_until=None, locked_by=None, progress_done=0, progress_total=0, error_code=None,
        error_detail=None, resource=None, execution_id=None, result=None, cancel_requested=False, created_at=now,
        updated_at=now, started_at=None, finished_at=None, principal_id=None, namespace=None,
    )
