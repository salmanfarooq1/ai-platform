"""api/errors.py: the standard error body and the handlers behind it (no external services)."""
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.errors import ErrorBody, _split_detail, error_response, register_exception_handlers
from api.middleware.logging import LoggingMiddleware, RequestIDMiddleware
from api.observability import request_id_var

pytestmark = pytest.mark.unit


class Body(BaseModel):
    name: str
    count: int


def make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.post("/items")
    async def items(body: Body):
        return body

    @app.get("/blocked")
    async def blocked():
        raise HTTPException(status_code=400, detail={"error": "query_blocked", "reason": "no injection"})

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="No documents found in namespace 'x'.")

    @app.get("/limited")
    async def limited():
        raise HTTPException(status_code=429, detail="slow down", headers={"Retry-After": "7"})

    @app.get("/boom")
    async def boom():
        raise ValueError("internal secret")

    return app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=make_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


def test_error_response_has_exactly_the_three_fields():
    token = request_id_var.set("req-abc")
    try:
        resp = error_response("some_code", "Some message", 418)
    finally:
        request_id_var.reset(token)
    assert resp.status_code == 418
    assert resp.body == b'{"error":{"code":"some_code","message":"Some message","request_id":"req-abc"}}'


def test_error_response_passes_headers_through():
    resp = error_response("c", "m", 429, headers={"Retry-After": "5"})
    assert resp.headers["retry-after"] == "5"


def test_error_body_model_round_trips():
    body = ErrorBody.model_validate({"error": {"code": "c", "message": "m", "request_id": "r"}})
    assert body.error.code == "c"


@pytest.mark.parametrize(("status", "detail", "expected"), [
    (404, "gone", ("not_found", "gone")),
    (400, {"error": "query_blocked", "reason": "bad"}, ("query_blocked", "bad")),
    (400, {"error": "query_blocked"}, ("query_blocked", "query_blocked")),
    (409, "conflict", ("http_409", "conflict")),
    (502, "upstream", ("bad_gateway", "upstream")),
    (503, {"message": "down"}, ("service_unavailable", "down")),
])
def test_split_detail(status, detail, expected):
    assert _split_detail(status, detail) == expected


async def test_validation_error_lists_every_bad_field(client):
    resp = await client.post("/items", json={"count": "x"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert "body.name: Field required" in err["message"]
    assert "body.count:" in err["message"]
    assert err["request_id"] == resp.headers["X-Request-ID"]


async def test_http_exception_with_dict_detail(client):
    resp = await client.get("/blocked")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "query_blocked"
    assert resp.json()["error"]["message"] == "no injection"


async def test_http_exception_headers_are_kept(client):
    resp = await client.get("/limited")
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "7"
    assert resp.json()["error"]["message"] == "slow down"


async def test_unknown_route_is_standard_404(client):
    resp = await client.get("/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_unhandled_exception_hides_details_and_logs_them(client, caplog):
    with caplog.at_level("ERROR"):
        resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["error"] == {
        "code": "internal_error",
        "message": "Internal server error",
        "request_id": resp.headers["X-Request-ID"],
    }
    assert "internal secret" not in resp.text
    assert any(r.exc_info and "internal secret" in str(r.exc_info[1]) for r in caplog.records)


async def test_trace_and_request_ids_are_32_hex_on_error_responses(client):
    resp = await client.get("/missing")
    for header in ("X-Request-ID", "X-Trace-ID"):
        value = resp.headers[header]
        assert len(value) == 32 and int(value, 16) >= 0
