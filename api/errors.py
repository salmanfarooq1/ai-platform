"""One error format for every failure: {"error": {"code", "message", "request_id"}}.

`error_response()` is used by middleware that must answer directly. The handlers
cover HTTPException (including router 404/405), request validation and any
unhandled exception. A 500 body never carries a stack trace: the traceback goes
to the structured log only.
"""
import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.observability import current_request_id
from gateway.types import Decision, GatewayDenied

logger = logging.getLogger("api.errors")

_STATUS_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limit_exceeded",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorBody(BaseModel):
    error: ErrorDetail


def _request_id(request: Request | None) -> str:
    if request is not None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return str(rid)
    return current_request_id()


def error_response(
    code: str,
    message: str,
    status: int,
    request: Request | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a standard error response."""
    body = ErrorBody(error=ErrorDetail(code=code, message=message, request_id=_request_id(request)))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=dict(headers) if headers else None)


def _split_detail(status: int, detail: Any) -> tuple[str, str]:
    """Map an HTTPException detail (str or {"error": code, "reason": text}) to (code, message)."""
    default_code = _STATUS_CODES.get(status, f"http_{status}")
    if isinstance(detail, dict):
        code = str(detail.get("error") or detail.get("code") or default_code)
        message = str(detail.get("reason") or detail.get("message") or code)
        return code, message
    return default_code, str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # registered for this type only
    code, message = _split_detail(exc.status_code, exc.detail)
    return error_response(code, message, exc.status_code, request, headers=exc.headers)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # registered for this type only
    parts = []
    for err in jsonable_encoder(exc.errors()):
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return error_response("validation_error", "; ".join(parts) or "Invalid request", 422, request)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response("internal_error", "Internal server error", 500, request)


# Gateway deny reasons that keep their own status and error code. Every other deny is 403 `policy_denied`.
_DENY_STATUS: dict[str, int] = {
    "rate_limit_exceeded": 429,
    "daily_token_budget_exceeded": 429,
    "cost_cap_exceeded": 429,
    "dependency_unavailable": 503,
    "decision_unrecorded": 503,
    "query_blocked": 400,
}


def decision_response(decision: Decision, request: Request | None = None) -> JSONResponse:
    """The standard error for a gateway deny. The reason code is in the message, internals never are."""
    status = _DENY_STATUS.get(decision.reason)
    if status is not None:
        return error_response(decision.reason, decision.message or decision.reason, status, request, headers=decision.headers)
    return error_response("policy_denied", f"Denied by policy (reason: {decision.reason})", 403, request)


async def gateway_denied_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GatewayDenied)  # registered for this type only
    return decision_response(exc.decision, request)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(GatewayDenied, gateway_denied_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
