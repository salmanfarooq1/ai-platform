"""api/observability.py: JSON log format, logging setup and tracing setup."""
import io
import json
import logging

import pytest
from fastapi import FastAPI
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import api.observability as obs
from api.observability import JsonFormatter, request_id_var, setup_logging, setup_tracing, trace_id_var
from core.settings import get_settings

pytestmark = pytest.mark.unit


def record(msg="hello %s", args=("world",), level=logging.INFO, **extra):
    r = logging.LogRecord("api.test", level, __file__, 1, msg, args, None)
    for k, v in extra.items():
        setattr(r, k, v)
    return r


def test_formatter_emits_one_json_object_with_ids():
    rid = request_id_var.set("rid-1")
    tid = trace_id_var.set("t" * 32)
    try:
        line = JsonFormatter().format(record())
    finally:
        request_id_var.reset(rid)
        trace_id_var.reset(tid)
    assert "\n" not in line
    data = json.loads(line)
    assert data["message"] == "hello world"
    assert data["level"] == "INFO"
    assert data["logger"] == "api.test"
    assert data["request_id"] == "rid-1"
    assert data["trace_id"] == "t" * 32
    assert data["timestamp"].endswith("+00:00")


def test_formatter_outside_a_request_uses_dash_placeholders():
    data = json.loads(JsonFormatter().format(record()))
    assert data["request_id"] == "-"
    assert data["trace_id"] == "-"


def test_formatter_includes_extra_fields_and_serialises_odd_values():
    data = json.loads(JsonFormatter().format(record(status=404, path="/x", weird={1, 2})))
    assert data["status"] == 404
    assert data["path"] == "/x"
    assert isinstance(data["weird"], str)


def test_formatter_includes_exception_text():
    try:
        raise KeyError("missing-key")
    except KeyError:
        import sys

        r = record()
        r.exc_info = sys.exc_info()
    data = json.loads(JsonFormatter().format(r))
    assert "KeyError: 'missing-key'" in data["exception"]
    assert data["exception"].startswith("Traceback")


def test_trace_id_comes_from_the_active_span():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("s") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        assert obs.current_trace_id() == expected
        assert json.loads(JsonFormatter().format(record()))["trace_id"] == expected
    assert not trace.get_current_span().get_span_context().is_valid
    assert len(obs.current_trace_id()) == 32  # fresh random id when there is no span


def test_setup_logging_replaces_foreign_handlers_and_is_idempotent(monkeypatch):
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    monkeypatch.setattr(obs.sys, "stdout", buf)
    try:
        root.addHandler(logging.StreamHandler(io.StringIO()))  # e.g. a Rich handler from a library
        setup_logging("WARNING")
        setup_logging("WARNING")
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        assert root.level == logging.WARNING
        logging.getLogger("uvicorn.error").warning("from uvicorn")
        logging.getLogger("api.x").info("below the level")
        lines = [json.loads(line) for line in buf.getvalue().splitlines()]
        assert [line["message"] for line in lines] == ["from uvicorn"]
        assert logging.getLogger("uvicorn.error").handlers == []
    finally:
        root.handlers = saved
        root.setLevel(saved_level)


def test_setup_logging_reads_level_from_settings(monkeypatch):
    root = logging.getLogger()
    saved, saved_level = root.handlers[:], root.level
    monkeypatch.setenv("LOG_LEVEL", "debug")
    get_settings.cache_clear()
    try:
        setup_logging()
        assert root.level == logging.DEBUG
    finally:
        root.handlers = saved
        root.setLevel(saved_level)
        monkeypatch.delenv("LOG_LEVEL")
        get_settings.cache_clear()


def _fresh_provider(monkeypatch, endpoint):
    monkeypatch.setattr(obs, "_provider", None)
    from opentelemetry import trace

    monkeypatch.setattr(trace, "set_tracer_provider", lambda p: None)  # keep the global provider untouched
    monkeypatch.chdir("/")  # no .env files
    if endpoint:
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    else:
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    get_settings.cache_clear()


def test_tracing_has_no_exporter_or_span_processor_by_default(monkeypatch):
    _fresh_provider(monkeypatch, None)
    try:
        provider = setup_tracing(FastAPI())
        assert provider._active_span_processor._span_processors == ()
        assert provider.resource.attributes["service.name"] == "ai-platform-api"
    finally:
        get_settings.cache_clear()


def test_tracing_adds_a_batch_exporter_only_when_endpoint_is_set(monkeypatch):
    _fresh_provider(monkeypatch, "http://collector.invalid:4318")
    try:
        provider = setup_tracing(FastAPI())
        processors = provider._active_span_processor._span_processors
        assert len(processors) == 1 and isinstance(processors[0], BatchSpanProcessor)
        provider.shutdown()  # stop the exporter thread
    finally:
        get_settings.cache_clear()
