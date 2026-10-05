"""Principal scopes, the require_scope dependency, and which paths need authentication."""
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import authenticate, require_scope
from api.errors import register_exception_handlers
from api.middleware.auth import PUBLIC_PATHS, requires_auth
from core.identity.models import ALL_SCOPES, Principal, Scope, parse_scopes


def principal(*scopes):
    return Principal(id=uuid4(), tenant_id=uuid4(), kind="service", scopes=frozenset(scopes))


def test_scope_values_are_the_documented_five():
    assert ALL_SCOPES == {"kb:read", "kb:write", "query", "agent", "audit:read", "admin"}


def test_has_scope_exact_match_only():
    p = principal("query")
    assert p.has_scope(Scope.QUERY) and p.has_scope("query")
    assert not p.has_scope(Scope.KB_WRITE)
    assert not p.has_scope("kb:read")


def test_admin_scope_satisfies_every_scope():
    p = principal("admin")
    assert all(p.has_scope(s) for s in Scope)


def test_no_scopes_grants_nothing():
    assert not any(principal().has_scope(s) for s in Scope)


def test_parse_scopes_drops_unknown_values():
    assert parse_scopes(["query", "root", "kb:read", ""]) == frozenset({"query", "kb:read"})


def test_principal_is_immutable():
    p = principal("query")
    with pytest.raises(AttributeError):
        p.tenant_id = uuid4()  # type: ignore[misc]  # frozen dataclass: the assignment is what is under test


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS))
def test_public_paths_need_no_credential(path):
    assert requires_auth(path) is False


@pytest.mark.parametrize("path", [
    "/v1", "/v1/search", "/v1/ingest", "/v1/documents", "/v1/config", "/v1/analytics/summary", "/v1/quality-report",
    "/v1/feedback", "/v1/agent/query", "/v1/mcp/sse", "/v1/mcp/messages/", "/v1/unknown",
])
def test_every_other_v1_path_needs_a_credential(path):
    assert requires_auth(path) is True


@pytest.mark.parametrize("path", ["/search", "/mcp/sse", "/nope", "/v10/search"])
def test_unversioned_or_foreign_paths_are_not_auth_gated(path):
    # they 404 (or are not ours); there is nothing behind them to protect
    assert requires_auth(path) is False


def make_app(state_principal):
    app = FastAPI()
    register_exception_handlers(app)

    @app.middleware("http")
    async def inject(request, call_next):
        if state_principal is not None:
            request.state.principal = state_principal
        return await call_next(request)

    @app.get("/who")
    async def who(p: Principal = Depends(authenticate)):
        return {"tenant": str(p.tenant_id)}

    @app.get("/needs-write")
    async def needs_write(p: Principal = Depends(require_scope(Scope.KB_WRITE))):
        return {"ok": True}

    return app


def test_authenticate_returns_the_principal_set_by_the_middleware():
    p = principal("query")
    resp = TestClient(make_app(p)).get("/who")
    assert resp.status_code == 200
    assert resp.json() == {"tenant": str(p.tenant_id)}


def test_authenticate_without_a_principal_is_401_with_the_standard_body():
    resp = TestClient(make_app(None)).get("/who")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
    assert resp.headers["www-authenticate"] == "Bearer"


def test_require_scope_without_the_scope_is_403_and_names_the_scope():
    resp = TestClient(make_app(principal("query", "kb:read"))).get("/needs-write")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"
    assert "kb:write" in resp.json()["error"]["message"]


def test_require_scope_with_the_scope_or_admin_passes():
    assert TestClient(make_app(principal("kb:write"))).get("/needs-write").status_code == 200
    assert TestClient(make_app(principal("admin"))).get("/needs-write").status_code == 200


def test_require_scope_without_a_principal_is_401_not_403():
    assert TestClient(make_app(None)).get("/needs-write").status_code == 401


def test_only_the_two_session_create_posts_are_exempt_from_auth_under_v1():
    """Every /v1 route and method is called with no credential and the middleware's refusal is observed. Only
    POST /v1/session and POST /v1/session/preview may get past the auth middleware. A newly exempted route must
    fail this test."""
    import logging
    import re

    from api.main import create_app

    class Collect(logging.Handler):
        def __init__(self):
            super().__init__(logging.INFO)
            self.messages: list[str] = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    collect = Collect()
    auth_logger = logging.getLogger("api.auth")
    auth_logger.setLevel(logging.INFO)
    auth_logger.addHandler(collect)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    # Every documented /v1 operation, plus the raw ASGI routes that are not in the schema (the MCP transport).
    calls = {(m.upper(), p) for p, ops in app.openapi()["paths"].items() if p.startswith("/v1") for m in ops}
    calls |= {("GET", "/v1/mcp/sse"), ("POST", "/v1/mcp/messages/")}
    exempt = set()
    for method, template in sorted(calls):
        path = re.sub(r"\{[^}]+\}", "x", template)
        collect.messages.clear()
        client.request(method, path)
        # The middleware logs "authentication failed" when it refuses. A route that gets past it (even if the
        # handler then answers 401 itself) leaves no such record.
        if not any("authentication failed" in m for m in collect.messages):
            exempt.add((method, path))
    auth_logger.removeHandler(collect)
    exempt -= {("GET", "/v1/health")}  # the documented public health route
    assert exempt == {("POST", "/v1/session"), ("POST", "/v1/session/preview")}
