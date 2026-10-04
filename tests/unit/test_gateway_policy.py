"""Policy documents: validation, the default policy, the engine seam and the error mapping."""
import json

import pytest

from api.errors import decision_response
from gateway import Decision, PolicyDocument, PolicyError, PythonPolicyEngine
from gateway.policy import DEFAULT_POLICY, PLATFORM_MAX_TOOL_CALLS, parse_policy


def test_default_policy_allows_every_resource_with_the_platform_limits():
    assert (DEFAULT_POLICY.allowed_kbs, DEFAULT_POLICY.allowed_tools, DEFAULT_POLICY.allowed_models) == ("*", "*", "*")
    assert DEFAULT_POLICY.max_tool_calls == PLATFORM_MAX_TOOL_CALLS == 50
    assert DEFAULT_POLICY.max_tokens_per_request == 100_000 and DEFAULT_POLICY.max_query_length == 1000
    assert DEFAULT_POLICY.blocked_terms == []


def test_a_document_that_leaves_a_list_out_allows_nothing_for_it():
    doc = PolicyDocument.model_validate({"allowed_kbs": ["legal"]})
    assert doc.allowed_models == [] and doc.allowed_tools == []


def test_valid_document_round_trips_and_the_wildcard_is_the_string_star():
    doc = parse_policy({"allowed_models": "*", "allowed_tools": ["retrieve_chunks"], "allowed_kbs": ["legal", "kyc_aml"],
                        "max_tool_calls": 4, "max_tokens_per_request": 2000, "max_query_length": 300, "blocked_terms": ["x"]})
    assert doc.allowed_models == "*" and doc.max_tool_calls == 4
    assert parse_policy(json.dumps(doc.model_dump())) == doc  # also accepts JSON text, as asyncpg returns jsonb


@pytest.mark.parametrize("bad", [
    {"allowed_kbs": "legal"},               # a bare string other than "*"
    {"allowed_kbs": ["legal", "*"]},        # wildcard inside a list
    {"allowed_kbs": ["", "legal"]},         # blank entry
    {"allowed_models": 5},
    {"max_tool_calls": -1},
    {"max_tool_calls": PLATFORM_MAX_TOOL_CALLS + 1},   # a policy cannot exceed the platform cap
    {"max_tokens_per_request": 0},
    {"max_query_length": 100_000},
    {"blocked_terms": ["ok", " "]},
    {"unknown_field": True},                # typos must not silently pass
    "not a document",
    [],
])
def test_invalid_documents_are_rejected(bad):
    with pytest.raises(PolicyError):
        parse_policy(bad)


def test_invalid_json_text_is_rejected():
    with pytest.raises(PolicyError):
        parse_policy("{not json")


async def test_python_engine_verdicts():
    from gateway import Action, ActionKind, build_boundary
    from tests.gateway_helpers import make_principal

    boundary = build_boundary(make_principal(("admin",)), PolicyDocument(allowed_kbs=["legal"], allowed_tools=["t"], allowed_models=["m"]))
    engine = PythonPolicyEngine()
    assert (await engine.evaluate(boundary, Action(ActionKind.KB_READ, "legal"))).allowed
    assert (await engine.evaluate(boundary, Action(ActionKind.KB_READ))).allowed  # no single resource: nothing to check
    assert (await engine.evaluate(boundary, Action(ActionKind.KB_READ, "x"))).reason == "kb_not_allowed"
    assert (await engine.evaluate(boundary, Action(ActionKind.TOOL_CALL))).reason == "tool_not_allowed"  # a tool call must name its tool
    assert (await engine.evaluate(boundary, Action(ActionKind.MODEL_INVOKE))).reason == "model_not_allowed"
    assert (await engine.evaluate(boundary, Action(ActionKind.AGENT_RUN))).allowed


def _body(decision):
    response = decision_response(decision)
    return response.status_code, json.loads(response.body), dict(response.headers)


@pytest.mark.parametrize("reason, status, code", [
    ("kb_not_allowed", 403, "policy_denied"),
    ("tool_not_allowed", 403, "policy_denied"),
    ("model_not_allowed", 403, "policy_denied"),
    ("token_limit", 403, "policy_denied"),
    ("tool_call_limit", 403, "policy_denied"),
    ("action_not_allowed", 403, "policy_denied"),
    ("policy_unavailable", 403, "policy_denied"),
    ("internal_error", 403, "policy_denied"),
    ("no_principal", 403, "policy_denied"),
    ("rate_limit_exceeded", 429, "rate_limit_exceeded"),
    ("daily_token_budget_exceeded", 429, "daily_token_budget_exceeded"),
    ("dependency_unavailable", 503, "dependency_unavailable"),
    ("query_blocked", 400, "query_blocked"),
])
def test_deny_reasons_map_to_the_documented_status_and_code(reason, status, code):
    got_status, body, _ = _body(Decision(allowed=False, stage="s", reason=reason, message="the message"))
    assert (got_status, body["error"]["code"]) == (status, code)
    assert set(body["error"]) == {"code", "message", "request_id"}


def test_a_policy_deny_names_the_reason_code_and_nothing_internal():
    _, body, _ = _body(Decision(allowed=False, stage="policy", reason="kb_not_allowed", message="internal detail"))
    assert body["error"]["message"] == "Denied by policy (reason: kb_not_allowed)"
    assert "internal detail" not in json.dumps(body)


def test_limit_denies_carry_their_headers():
    _, _, headers = _body(Decision(allowed=False, stage="rate", reason="rate_limit_exceeded", message="slow down",
                                   headers={"Retry-After": "5", "X-RateLimit-Remaining": "0"}))
    assert headers["retry-after"] == "5" and headers["x-ratelimit-remaining"] == "0"
