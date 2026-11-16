"""Model identity and failure records on real API requests."""
import json
from dataclasses import replace

pytest_plugins = ("tests.e2e.conftest",)


async def test_model_invoke_record_carries_extension(client, make_client, database_url, pool, tenant_a,
                                                    fake_llm, fake_embeddings):
    from api.routers.search import LLM_CONFIG
    from config import completion_fallbacks_for_mode
    from core.settings import get_settings
    from tests.e2e.test_search_flow import GDPR, QUERY
    from tests.jobs_helpers import post_ingest

    await post_ingest(client, params={"namespace": "legal"}, files={"file": ("gdpr.md", GDPR, "text/markdown")})
    response = await client.post("/v1/search", json=QUERY)
    assert response.status_code == 200, response.text
    rows = await pool.fetch(
        "SELECT id, record_version, extensions FROM gateway_decisions WHERE request_id = $1 AND action = 'model.invoke' ORDER BY created_at, id",
        response.headers["X-Request-ID"],
    )
    assert rows
    for row in rows:
        extensions = row["extensions"] if isinstance(row["extensions"], dict) else json.loads(row["extensions"])
        assert row["record_version"] == 2
        configured = {
            LLM_CONFIG["model"], LLM_CONFIG["embedding_model"],
            *completion_fallbacks_for_mode(get_settings().mode), *get_settings().embed_fallbacks,
        }
        assert extensions["model"]["name"] in configured
        assert extensions["model"]["route"].startswith("sha256:")
    attempt = next(row for row in rows if (
        row["extensions"] if isinstance(row["extensions"], dict) else json.loads(row["extensions"])
    )["model"]["phase"] == "attempt")
    from tests.e2e.web_helpers import key_with

    audit_key, _ = key_with(database_url, tenant_a, ["audit:read"])
    audit_client = make_client({"Authorization": f"Bearer {audit_key}"})
    receipt = await audit_client.get(f"/v1/receipts/{attempt['id']}")
    assert receipt.status_code == 200
    canonical = receipt.json()["canonical"]
    if isinstance(canonical, str):
        canonical = json.loads(canonical)
    assert canonical["decision"]["extensions"]["model"]["route"].startswith("sha256:")


async def test_catalog_failure_is_recorded_before_io(client, app, pool, fake_llm, fake_embeddings):
    from api.routers.search import LLM_CONFIG
    from ports.errors import ModelDigestMismatch, ResidencyUnknown, UnknownModel, UnpricedModel
    from tests.fakes import FakeCatalog

    reasons = [
        (UnknownModel("unknown model"), "model_unknown"),
        (ModelDigestMismatch("digest mismatch"), "model_digest_mismatch"),
        (UnpricedModel("unpriced model"), "model_unpriced"),
        (ResidencyUnknown("residency unknown"), "residency_unknown"),
    ]
    before = len(fake_llm.calls)
    for index, (failure, reason) in enumerate(reasons):
        app.state.adapters = replace(
            app.state.adapters, model_catalog=FakeCatalog(failures={LLM_CONFIG["model"]: failure}),
        )
        response = await client.post("/v1/search", json={"query": f"failure query {index}", "namespace": "legal"})
        assert response.status_code == 403
        row = await pool.fetchrow(
            "SELECT outcome, reason FROM gateway_decisions WHERE request_id = $1 AND action = 'model.invoke' ORDER BY created_at DESC LIMIT 1",
            response.headers["X-Request-ID"],
        )
        assert row["outcome"] == "deny" and row["reason"] == reason
    assert len(fake_llm.calls) == before
    assert fake_embeddings.calls == []


async def test_secret_sentinel_not_in_record_receipt_or_error(client, app, pool, monkeypatch, json_logs):
    from api.routers.search import LLM_CONFIG
    from ports.errors import UnpricedModel
    from tests.fakes import FakeCatalog

    sentinel = "sk-SENTINEL-7f3a"
    monkeypatch.setenv("AZURE_OAI_KEY", sentinel)
    app.state.adapters = replace(
        app.state.adapters, model_catalog=FakeCatalog(failures={LLM_CONFIG["model"]: UnpricedModel("model is not priced")}),
    )
    response = await client.post("/v1/search", json={"query": "sentinel query", "namespace": "legal"})
    assert sentinel not in response.text
    rows = await pool.fetch("SELECT reason, extensions::text AS extensions FROM gateway_decisions")
    assert sentinel not in repr(rows)
    assert sentinel not in repr(json_logs())
