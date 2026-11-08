"""Optional route denial retains credential authority and trusted attribution."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from api.errors import register_exception_handlers
from api.gateway_deps import gateway_context
from api.module_routes import DISABLED_AGENT_ROUTES, mount_optional_routes
from core.identity.run_tokens import RunGrant
from core.modules import MODULE_NAMES
from gateway import Action, ActionKind, EnforcementContext, require
from tests.gateway_helpers import make_ctx, make_principal, make_runtime


class CaptureSink:
    def __init__(self):
        self.entries = []

    async def write(self, entry, events=None):
        self.entries.append(entry)
        return uuid4()


def app_for(principal, grant=None, *, mount_enabled=frozenset({"gateway"})):
    app = FastAPI()
    register_exception_handlers(app)
    runtime = make_runtime()
    runtime.enabled_modules = frozenset({"gateway"})
    sink = CaptureSink()
    runtime.decisions = sink
    app.state.gateway_runtime = runtime

    @app.middleware("http")
    async def verified_credential_fixture(request, call_next):
        # Match the existing auth-dependency unit harness: production middleware
        # verifies credentials; here its resulting authority is the fixture.
        request.state.principal = principal
        request.state.run_grant = grant
        return await call_next(request)

    mount_optional_routes(app, mount_enabled)
    return app, sink


@pytest.mark.parametrize("method,path,scopes,kind,resource", [
    ("POST", "/v1/agent/query", ("agent",), "agent.run", None),
    ("GET", "/v1/agent/runs", ("agent",), "kb.read", None),
    ("GET", "/v1/agent/runs/any-run", ("audit:read",), "audit.read", "runs"),
    ("GET", "/v1/mcp/sse", ("query",), "kb.read", None),
    ("HEAD", "/v1/mcp/sse", ("query",), "kb.read", None),
    ("POST", "/v1/mcp/messages", ("query",), "kb.read", None),
    ("POST", "/v1/mcp/messages/", ("kb:read",), "kb.read", None),
    ("POST", "/v1/mcp/messages/nested", ("kb:read",), "kb.read", None),
])
def test_disabled_routes_record_exact_entry_action_and_ignore_caller_module(method, path, scopes, kind, resource):
    app, sink = app_for(make_principal(scopes))
    response = TestClient(app).request(method, path, params={"required_module": "gateway"},
                                     headers={"X-Required-Module": "gateway"}, json={"required_module": "gateway"})
    assert response.status_code == 404
    if method != "HEAD":
        assert response.json()["error"]["code"] == "module_disabled"
    assert len(sink.entries) == 1
    entry = sink.entries[0]
    assert (entry.action, entry.resource, entry.outcome, entry.stage, entry.reason) == (
        kind, resource, "deny", "module", "module_disabled",
    )
    assert not app.state.mcp_mounted


def test_missing_identity_and_scope_precede_disabled_module():
    app, sink = app_for(None)
    assert TestClient(app).post("/v1/agent/query").status_code == 401
    assert sink.entries == []
    app, sink = app_for(make_principal(("kb:read",)))
    response = TestClient(app).post("/v1/agent/query")
    assert response.status_code == 403
    assert sink.entries[-1].reason == "missing_scope" and sink.entries[-1].stage == "boundary"
    app, sink = app_for(make_principal(()))
    assert TestClient(app).get("/v1/mcp/sse").status_code == 403
    assert all(entry.reason != "module_disabled" for entry in sink.entries)


def test_manifest_covers_every_registered_agent_and_sandbox_route_method():
    from api.agent.router import router as agent_router
    from api.routers.sandbox import router as sandbox_router

    actual = {(route.path, method) for router in (agent_router, sandbox_router)
              for route in router.routes for method in route.methods}
    manifest = {(spec.path, method) for spec in DISABLED_AGENT_ROUTES for method in spec.methods}
    assert actual <= manifest, actual - manifest
    assert {("/mcp/sse", "GET"), ("/mcp/sse", "HEAD"), ("/mcp/messages/", "POST")} <= manifest


def grant_for(principal):
    return RunGrant(principal=principal, execution_id=uuid4(), boundary=make_ctx(principal=principal).boundary.to_payload(),
                    token_id=uuid4(), expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))


@pytest.mark.parametrize("suffix,kind,resource", [
    ("model", "model.invoke", None), ("tools/retrieve_chunks", "tool.call", "retrieve_chunks"),
])
def test_disabled_sandbox_keeps_run_binding_and_execution_id(monkeypatch, suffix, kind, resource):
    import gateway.context

    async def no_prior_calls(*args):
        return 0

    monkeypatch.setattr(gateway.context, "count_run_tool_calls", no_prior_calls)
    principal = make_principal(("agent",))
    grant = grant_for(principal)
    path = f"/v1/sandbox/runs/{grant.execution_id}/{suffix}"
    ordinary, sink = app_for(principal)
    assert TestClient(ordinary).post(path).status_code == 403 and sink.entries == []
    wrong, sink = app_for(principal, grant_for(principal))
    assert TestClient(wrong).post(path).status_code == 403 and sink.entries == []
    matching, sink = app_for(principal, grant)
    response = TestClient(matching).post(path, json={"required_module": "gateway"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "module_disabled"
    assert len(sink.entries) == 1
    entry = sink.entries[0]
    assert (entry.action, entry.resource, entry.reason, entry.execution_id) == (
        kind, resource, "module_disabled", grant.execution_id,
    )


def test_enabled_router_attribution_survives_fastapi_inclusion(monkeypatch):
    import api.module_routes

    router = APIRouter()
    seen = []

    @router.get("/agent/probe")
    async def probe(ctx: EnforcementContext = Depends(gateway_context)):
        # A gateway action alone would not identify an optional agent route.
        seen.append(ctx.required_module)
        await require(ctx, Action(ActionKind.KB_READ))
        return {"ok": True}

    async def unused_transport(scope, receive, send):
        raise AssertionError("the transport must not run in this test")

    def registered_module(name):
        if name == "api.mcp.transport":
            return SimpleNamespace(handle_messages=unused_transport, handle_sse=unused_transport)
        return SimpleNamespace(router=router if name == "api.agent.router" else APIRouter())

    monkeypatch.setattr(api.module_routes, "import_module", registered_module)
    app, sink = app_for(make_principal(("query",)), mount_enabled=MODULE_NAMES)
    assert app.state.mcp_mounted
    response = TestClient(app).get("/v1/agent/probe")
    assert response.status_code == 404 and sink.entries[-1].reason == "module_disabled"
    assert seen == ["agents"]


def test_fresh_disabled_requests_load_no_optional_execution_package():
    script = '''
import json, sys
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.errors import register_exception_handlers
from api.module_routes import mount_optional_routes
from gateway import GatewayRuntime, build_boundary
from core.identity.run_tokens import RunGrant
from tests.gateway_helpers import FakeRedis, make_principal
import gateway.policy
import gateway.context
async def default_policy(*args):
    return None, None
gateway.policy.load_active_policy = default_policy
async def no_prior_calls(*args):
    return 0
gateway.context.count_run_tool_calls = no_prior_calls
principal = make_principal(('agent','query'))
grant = RunGrant(principal, uuid4(), build_boundary(principal, None, None).to_payload(), uuid4(),
                 datetime.now(timezone.utc) + timedelta(minutes=5))
class Sink:
    async def write(self, entry, events=None):
        return uuid4()
app = FastAPI()
register_exception_handlers(app)
app.state.gateway_runtime = GatewayRuntime(pool=None, cache=FakeRedis(), decisions=Sink(), enabled_modules=frozenset({'gateway'}))
@app.middleware('http')
async def credential_fixture(request, call_next):
    request.state.principal = principal
    request.state.run_grant = grant
    return await call_next(request)
mount_optional_routes(app, frozenset({'gateway'}))
client = TestClient(app)
statuses = [client.post('/v1/agent/query').status_code, client.get('/v1/agent/runs').status_code,
            client.get('/v1/mcp/sse').status_code, client.post('/v1/mcp/messages/').status_code,
            client.post(f'/v1/sandbox/runs/{grant.execution_id}/model').status_code]
prefixes = ('api.agent', 'api.mcp', 'api.routers.sandbox', 'adapters.openshell', 'mcp', 'langgraph')
loaded = sorted(name for name in sys.modules if any(name == p or name.startswith(p+'.') for p in prefixes))
print(json.dumps({'statuses': statuses, 'loaded': loaded}))
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    actual = json.loads(result.stdout.splitlines()[-1])
    assert actual == {"statuses": [404, 404, 404, 404, 404], "loaded": []}
