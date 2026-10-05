"""Sprint 009 QA fixes that need no database: L2 (agent-reported fields), L3 (refused connections keep three fields),
M3 (no regex in tool schemas, and a time limit on the check)."""
import asyncio
import time
from datetime import datetime, timezone

import pytest

from adapters.openshell_events import event_from_log
from adapters.sandbox_events import clean_detail
from api.agent.response import AGENT_REPORTED, build_sandbox_result
from gateway import Action, ActionKind, PolicyDocument, PolicyError, PythonPolicyEngine, build_boundary
from gateway import policy as policy_module
from gateway.policy import parse_policy
from ports import SandboxEventKind
from tests.gateway_helpers import make_principal

pytestmark = pytest.mark.unit
NOW = datetime.now(timezone.utc)


# ---- L2
def test_l2_a_sandboxed_answer_marks_what_the_agent_wrote_itself_and_an_in_process_one_does_not():
    out = {"answer": "x", "confidence": 0.9, "citations": [], "usage": {"prompt_tokens": 1}}
    result = build_sandbox_result(out, "q", "ns", 1.0)
    assert result["response"]["agent_reported"] == list(AGENT_REPORTED) == ["citations", "confidence", "usage"]
    assert result["usage"]["agent_reported"] is True
    from api.agent.schemas import AgentResponse

    assert AgentResponse(question="q", answer="a", reasoning_steps=[], tool_calls_made=0, total_time_seconds=0).agent_reported == []


# ---- L3
def test_l3_a_refused_connection_keeps_host_port_and_reason_and_nothing_free_form():
    detail = {"host": "api.example.com", "port": 443, "reason": "transparent_tcp_policy_denied", "message": "secret-ish text sk-123",
              "path": "/x", "source": "agent", "limit": "l"}
    assert clean_detail(detail, kind=SandboxEventKind.NETWORK_DENIED) == {"host": "api.example.com", "port": 443, "reason": "transparent_tcp_policy_denied"}
    assert "message" in clean_detail(detail, kind=SandboxEventKind.LOG)  # other kinds are unchanged


def test_l3_the_reason_comes_from_the_log_line_and_the_message_is_gone_from_the_row():
    event = event_from_log("INFO", "NET:OPEN [MED] DENIED /usr/bin/python3.10(0) -> api.openai.com:443 [reason:transparent_tcp_policy_denied]", {}, NOW)
    assert event is not None and event.detail["reason"] == "transparent_tcp_policy_denied"
    from adapters.sandbox_events import to_row

    assert set(to_row(event).detail) == {"host", "port", "reason"}


# ---- M3
@pytest.mark.parametrize("schema", [
    {"type": "string", "pattern": "^(a+)+$"},
    {"type": "object", "patternProperties": {"^(a+)+$": {"type": "string"}}},
    {"type": "string", "format": "email"},
    {"type": "object", "properties": {"q": {"type": "array", "items": {"type": "string", "pattern": "x"}}}},
    {"anyOf": [{"type": "integer"}, {"type": "string", "pattern": "x"}]},
    {"$defs": {"s": {"pattern": "x"}}, "type": "object"},
])
def test_m3_a_schema_with_a_regex_is_refused(schema):
    with pytest.raises(PolicyError):
        parse_policy({"tool_arguments": {"retrieve_chunks": schema}})


def test_m3_a_property_that_is_merely_named_pattern_or_format_is_fine_and_enums_and_lengths_work():
    schema = {"type": "object", "properties": {"pattern": {"type": "string", "maxLength": 10}, "format": {"enum": ["a", "b"]}}}
    assert parse_policy({"tool_arguments": {"retrieve_chunks": schema}}).tool_arguments["retrieve_chunks"] == schema


async def test_m3_a_slow_check_is_a_deny_and_does_not_stall_the_event_loop(monkeypatch):
    monkeypatch.setattr(policy_module, "SCHEMA_CHECK_SECONDS", 0.05)
    monkeypatch.setattr(policy_module, "schema_allows", lambda schema, args: time.sleep(0.5) or True)
    boundary = build_boundary(make_principal(("agent",)), PolicyDocument(allowed_models="*", allowed_tools="*", allowed_kbs="*", tool_arguments={"retrieve_chunks": {"type": "object"}}))
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    verdict = await PythonPolicyEngine().evaluate(boundary, Action(ActionKind.TOOL_CALL, "retrieve_chunks", arguments={}))
    task.cancel()
    assert (verdict.allowed, verdict.reason) == (False, "tool_argument_not_allowed")
    assert ticks >= 3  # the loop kept running while the check was stuck
