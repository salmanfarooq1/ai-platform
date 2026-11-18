import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import pytest

from tests.e2e.test_gateway_e2e import publish
from tests.e2e.test_search_flow import QUERY
from tests.fakes import FakeEmbeddings, FakeLLM

pytest_plugins = ("tests.e2e.conftest",)
pytestmark = pytest.mark.integration


@pytest.fixture
def recording_ollama():
    requests = []

    def record(request):
        requests.append(request)
        return httpx.Response(200, json={})

    return requests, httpx.MockTransport(record)


@pytest.fixture
def fake_llm(recording_ollama, platform_config, monkeypatch):
    import config
    from core.settings import get_settings

    monkeypatch.setitem(config.LLM_CONFIG, "model", str(get_settings().llm_model))

    class RecordingLLM(FakeLLM):
        async def complete_resolved(self, resolved, messages, *, max_tokens, response_format=None):
            async with httpx.AsyncClient(transport=recording_ollama[1]) as client:
                await client.post("http://ollama/api/generate")
            return await super().complete_resolved(resolved, messages, max_tokens=max_tokens, response_format=response_format)

    return RecordingLLM()


@pytest.fixture
def fake_embeddings(recording_ollama):
    class RecordingEmbeddings(FakeEmbeddings):
        async def embed_resolved(self, resolved, texts):
            async with httpx.AsyncClient(transport=recording_ollama[1]) as client:
                await client.post("http://ollama/api/embed")
            return await super().embed_resolved(resolved, texts)

    return RecordingEmbeddings()


async def test_denied_search_makes_no_model_request(make_client, pool, tenant_a, database_url, fake_llm, fake_embeddings, recording_ollama):
    from core.identity.admin import admin_connection, create_key, create_principal
    from core.settings import get_settings

    with admin_connection(database_url) as conn:
        principal = create_principal(conn, tenant_a.slug, "user", "reference-consumer")
        key = create_key(conn, principal, ["query"])
    client = make_client({"Authorization": f"Bearer {key.token}"})
    publish(database_url, tenant_a, {"allowed_kbs": "*", "allowed_models": [str(get_settings().embed_model)], "allowed_tools": "*"})
    chat_before = len(fake_llm.calls)
    embeddings_before = len(fake_embeddings.calls)
    ollama_requests_before = len(recording_ollama[0])
    response = await client.post("/v1/search", json=QUERY)
    assert response.status_code == 403
    assert "model_not_allowed" in response.json()["error"]["message"]
    assert len(fake_llm.calls) == chat_before
    assert len(fake_embeddings.calls) == embeddings_before
    assert len(recording_ollama[0]) == ollama_requests_before
    rows = await pool.fetch("SELECT reason, extensions FROM gateway_decisions WHERE request_id = $1", response.headers["X-Request-ID"])
    denied = [row for row in rows if row["reason"] == "model_not_allowed"]
    assert len(denied) == 1
    extensions = denied[0]["extensions"]
    if isinstance(extensions, str):
        extensions = json.loads(extensions)
    assert extensions["model"]["phase"] == "admission"
    assert extensions["model"]["source"] == "local"
    assert extensions["model"]["name"] == str(get_settings().llm_model)


def test_ollama_reachable_only_through_recorder(database_url, app_database_url, tmp_path):
    from core.identity.admin import admin_connection, create_key, create_principal
    from core.models_files import load_models_lock
    from scripts.showcase.m0 import Proxy, server_environment
    from tests.db_fixtures import _make_tenant
    from tests.harness import REDIS_URL

    models = [{"name": item.alias.removeprefix("ollama/"), "digest": item.digest.removeprefix("sha256:")} for item in load_models_lock()]

    class Recorder(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def do_GET(self):
            self.server.requests.append(("GET", self.path))
            data = json.dumps({"models": models}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.server.requests.append(("POST", self.path))
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    class RecordingProxy(Proxy):
        def forward(self):
            self.server.requests.append((self.command, self.path))
            super().forward()

        do_GET = forward
        do_POST = forward

    recorder = ThreadingHTTPServer(("127.0.0.1", 0), RecordingProxy)
    decoy = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    recorder.requests, decoy.requests, upstream.requests = [], [], []
    recorder.upstream = f"http://127.0.0.1:{upstream.server_port}"
    for server in (recorder, decoy, upstream):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        recorder_url = f"http://127.0.0.1:{recorder.server_port}"
        decoy_url = f"http://127.0.0.1:{decoy.server_port}"
        inherited = dict(os.environ, REDIS_URL=REDIS_URL, OLLAMA_API_BASE=decoy_url, OLLAMA_HOST=decoy_url, OLLAMA_URL=decoy_url,
                         OLLAMA_UNEXPECTED_OVERRIDE=decoy_url)
        env = server_environment(inherited, recorder_url, 5)
        env["DECOY_ENDPOINT"] = decoy_url
        env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        assert env["OLLAMA_BASE_URL"] == recorder_url
        assert all(env[name] == decoy_url for name in
                   ("OLLAMA_API_BASE", "OLLAMA_HOST", "OLLAMA_URL", "OLLAMA_UNEXPECTED_OVERRIDE"))
        program = r'''
import os
for name in ("OLLAMA_API_BASE", "OLLAMA_HOST", "OLLAMA_URL", "OLLAMA_UNEXPECTED_OVERRIDE"):
    os.environ[name] = os.environ["DECOY_ENDPOINT"]
import litellm
sdk_default = litellm.api_base
from scripts.showcase import m0_server
for name in ("OLLAMA_API_BASE", "OLLAMA_HOST", "OLLAMA_URL", "OLLAMA_UNEXPECTED_OVERRIDE"):
    assert os.environ[name] == os.environ["DECOY_ENDPOINT"]
assert litellm.api_base == sdk_default
import asyncio
from types import SimpleNamespace
import httpx
import litellm
from ports.models import ModelUse

async def fake_completion(**kwargs):
    url = kwargs.get("api_base") or os.environ["DECOY_ENDPOINT"]
    async with httpx.AsyncClient() as client:
        response = await client.post(url + "/api/generate", json={})
        assert response.status_code == 503
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")], usage=None)

litellm.acompletion = fake_completion
async def main():
    import config
    from adapters.model_catalog import build_model_catalog
    from core.settings import get_settings
    catalog = build_model_catalog(get_settings(), model_pricing=config.MODEL_PRICING)
    assert catalog.local.endpoint == os.environ["SHOWCASE_OLLAMA_PROXY"]
    assert litellm.api_base == sdk_default
    model = next(item for item in catalog.local.models.values() if ModelUse.COMPLETION in item.use)
    resolved = await catalog.local.resolve(model.alias, use=ModelUse.COMPLETION)
    assert resolved.route.endpoint == os.environ["SHOWCASE_OLLAMA_PROXY"]
    from adapters.registry import build_adapters
    from core.settings import get_settings
    llm = build_adapters(get_settings(), pool=object()).llm
    await llm.complete_resolved(resolved, [{"role": "user", "content": "test"}], max_tokens=1)
    await llm.complete([{"role": "user", "content": "test"}], model=model.alias, max_tokens=1)
asyncio.run(main())
'''
        result = subprocess.run([sys.executable, "-c", program], env=env, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr
        assert any(method == "GET" and path == "/api/tags" for method, path in recorder.requests)
        assert sum(method == "POST" for method, _ in recorder.requests) == 2
        assert upstream.requests == [("GET", "/api/tags")]
        assert decoy.requests == []

        tenant = _make_tenant(database_url, "m0-recorder-" + uuid4().hex[:12])
        with admin_connection(database_url) as conn:
            keys = {}
            for name, scope in (("CONSUMER", "query"), ("AUDITOR", "audit:read"), ("AGENT_DEVELOPER", "agent")):
                principal = create_principal(conn, tenant.slug, "user", "m0-" + name.lower())
                keys["SHOWCASE_KEY_" + name] = create_key(conn, principal, [scope]).token
        journey_env = dict(inherited, MIGRATION_DATABASE_URL=database_url, DATABASE_URL=app_database_url,
                           DEPLOY_SHAPE="multi_tenant", ENABLED_MODULES="gateway", MODE="local",
                           LLM_MODEL="ollama/qwen3:4b-instruct-2507-q4_K_M", OBJECT_STORE_DIR=str(tmp_path / "objects"),
                           SHOWCASE_FIXTURE_KEY=tenant.tokens["full"], SHOWCASE_OLLAMA_UPSTREAM=recorder.upstream,
                           LITELLM_LOCAL_MODEL_COST_MAP="True",
                           TEST_STATE_DIR=str(tmp_path / ".showcase"),
                           TEST_MANIFEST=json.dumps({"tenant_id": tenant.id, "tenant_slug": tenant.slug}),
                           TEST_KEYS="\n".join(f"{name}={value}" for name, value in keys.items()))
        journey = r'''
import os
from pathlib import Path
from scripts.showcase import m0
m0.STATE = Path(os.environ["TEST_STATE_DIR"])
m0.STATE.mkdir(mode=0o700)
m0.private_state = lambda name: os.environ["TEST_MANIFEST"] if name == "manifest.json" else os.environ["TEST_KEYS"]
m0.finish_with_drill = lambda **kwargs: int(kwargs["failed"])  # this test is the journey; the drill has its own live test
raise SystemExit(m0.main())
'''
        decoy.requests.clear()
        upstream.requests.clear()
        result = subprocess.run([sys.executable, "-c", journey], env=journey_env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout
        assert "PASS search: model admission denied; Ollama request count unchanged" in result.stdout
        assert "PASS receipt:" in result.stdout
        assert "PASS restore:" in result.stdout
        assert any(method == "GET" and path == "/api/tags" for method, path in upstream.requests)
        assert all(method != "POST" for method, _ in upstream.requests)
        assert decoy.requests == []
    finally:
        for server in (recorder, decoy, upstream):
            server.shutdown()
            server.server_close()


async def test_gateway_only_auditor_reads_request_decisions(database_url, app_database_url, tenants, monkeypatch):
    from asgi_lifespan import LifespanManager

    import api.main
    import core.database.pool
    from adapters.redis_cache import RedisCache
    from core.identity.admin import admin_connection, create_key
    from tests.harness import REDIS_URL

    tenant, foreign = tenants
    configured = api.main.settings.model_copy(update={"deploy_shape": "multi_tenant", "enabled_modules": "gateway"})
    monkeypatch.setattr(api.main, "settings", configured)
    monkeypatch.setitem(core.database.pool.DATABASE_CONFIG, "url", app_database_url)
    with admin_connection(database_url) as conn:
        auditor = create_key(conn, tenant.principal_id, ["audit:read"])
        other_auditor = create_key(conn, foreign.principal_id, ["audit:read"])
    app = api.main.create_app(adapter_overrides={"cache": RedisCache(REDIS_URL, configured.embedding_dim)})
    async with LifespanManager(app), httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        disabled = await client.post("/v1/agent/query", headers=tenant.headers("full"), json={"question": "Check policy"})
        assert disabled.status_code == 404 and disabled.json()["error"]["code"] == "module_disabled"
        request_id = disabled.headers["x-request-id"]
        decisions = await client.get("/v1/decisions", params={"request_id": request_id},
                                     headers={"Authorization": "Bearer " + auditor.token})
        assert decisions.status_code == 200
        assert [(row["request_id"], row["reason"]) for row in decisions.json()["items"]] == [(request_id, "module_disabled")]
        forbidden = await client.get("/v1/decisions", params={"request_id": request_id}, headers=tenant.headers("query_only"))
        assert forbidden.status_code == 403
        foreign_rows = await client.get("/v1/decisions", params={"request_id": request_id},
                                        headers={"Authorization": "Bearer " + other_auditor.token})
        assert foreign_rows.status_code == 200 and foreign_rows.json()["items"] == []


def test_reference_company_seed_allows_models(database_url, tmp_path):
    import time

    from core.identity.admin import admin_connection
    from gateway.admin import show_policy

    state_file = tmp_path / "state.json"
    process = subprocess.Popen(
        [sys.executable, "-m", "scripts.e2e.serve", "--reference-company", "--enabled-modules", "gateway",
         "--port", "0", "--state-dir", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 90
        while not state_file.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert state_file.exists(), "reference-company startup did not publish state"
        state = json.loads(state_file.read_text())
        with admin_connection(state["owner_dsn"]) as conn:
            head = show_policy(conn, state["tenant"])
            with conn.cursor() as cur:
                cur.execute("SELECT version, document FROM policies WHERE tenant_id = (SELECT id FROM tenants WHERE slug = %s) ORDER BY version", (state["tenant"],))
                history = cur.fetchall()
        assert head["version"] == 1
        assert head["document"]["allowed_models"] == "*"
        assert len(history) == 1
    finally:
        process.terminate()
        process.communicate(timeout=30)


async def test_journey_denies_only_selected_alias(database_url, db_pool, tenant_a):
    from core.identity.admin import admin_connection
    from core.models_files import load_models_lock
    from gateway.admin import set_policy, show_policy
    from scripts.showcase.m0 import publish_journey_policy

    aliases = [entry.alias for entry in load_models_lock()]
    assert len(aliases) > 1
    baseline = {"allowed_kbs": "*", "allowed_tools": "*", "allowed_models": "*"}
    with admin_connection(database_url) as conn:
        set_policy(conn, tenant_a.slug, baseline, "test")
        before, version, _ = publish_journey_policy(conn, tenant_a.slug, ["default"], aliases[0])
        head = show_policy(conn, tenant_a.slug)
    assert head["version"] == version
    assert aliases[0] not in head["document"]["allowed_models"]
    assert aliases[1] in head["document"]["allowed_models"]
    assert {**head["document"], "allowed_models": "*"} == before
    from unittest.mock import AsyncMock

    from api.services.model_calls import ModelCaller
    from core.settings import Settings
    from gateway import GatewayDenied
    from ports.models import ModelUse
    from tests.fakes import FakeCatalog, FakeModelLimitStore, fake_resolved_model
    from tests.integration.test_gateway import context_for

    provider = AsyncMock()
    resolved = fake_resolved_model(aliases[0], ModelUse.COMPLETION)
    caller = ModelCaller(FakeCatalog({aliases[0]: resolved}), provider, FakeModelLimitStore(), settings=Settings())
    with pytest.raises(GatewayDenied) as denied:
        await caller.complete(await context_for(db_pool, tenant_a), aliases[0], [], max_tokens=1)
    assert denied.value.decision.reason == "model_not_allowed"
    provider.complete_resolved.assert_not_awaited()
