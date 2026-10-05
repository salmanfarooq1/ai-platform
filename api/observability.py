"""Structured logging and tracing.

- `JsonFormatter` writes one JSON object per line, always carrying `request_id` and `trace_id`.
- `setup_logging()` installs it on the root logger (and uvicorn's loggers).
- `setup_tracing(app)` configures the OpenTelemetry SDK with FastAPI instrumentation.
  An OTLP exporter (and its background thread) is created only when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Otherwise spans are created but never exported.

Deferred: DB, Redis and LLM spans (Sprint 005 adapters are the seam).
"""
import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.settings import get_settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")

# Attributes that exist on every LogRecord. Anything else came from `extra=`.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def new_request_id() -> str:
    return uuid.uuid4().hex


def current_trace_id() -> str:
    """32-hex trace id of the active span, or a fresh random id when no valid span is active."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return uuid.uuid4().hex


def current_request_id() -> str:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """One JSON object per line with request_id and trace_id."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = trace_id_var.get()
        if trace_id == "-":
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "trace_id": trace_id,
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Route all logging through the JSON formatter on stdout. Safe to call twice."""
    level_name = (level or get_settings().log_level).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.set_name("json-stdout")

    # Replace every root handler: libraries such as the MCP SDK call logging.basicConfig()
    # with a Rich console handler on import, which would print non-JSON lines.
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level_name)

    # uvicorn and litellm install their own plain-text handlers. Hand their records to the root handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True

    # (litellm's "Give Feedback / Get Help" banner is silenced by the LiteLLM adapter, adapters/litellm_llm.py.)


_provider: TracerProvider | None = None


def setup_tracing(app: FastAPI) -> TracerProvider:
    """Configure the OTel SDK and instrument the app. No exporter unless OTLP is configured."""
    global _provider
    settings = get_settings()
    if _provider is None:
        provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        if settings.otel_exporter_otlp_endpoint:
            # Imported lazily: the exporter pulls in an HTTP client and starts a thread.
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _provider = provider
    FastAPIInstrumentor.instrument_app(app, tracer_provider=_provider)
    return _provider
