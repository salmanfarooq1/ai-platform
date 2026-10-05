"""Sprint 009: a policy can set a JSON Schema per tool, and the gateway checks the arguments of a tool call against it.

These tests cover the document (what a policy may contain), the engine verdict, the boundary that carries the schemas to
a worker, and the reason code. The deny row itself is written by `enforce()` and is tested against Postgres in
`tests/integration/test_tool_argument_deny.py`.
"""
import json

import pytest

from gateway import Action, ActionKind, PolicyDocument, PolicyError, PythonPolicyEngine, build_boundary
from gateway.boundary import ExecutionBoundary
from gateway.policy import MAX_TOOL_SCHEMA_BYTES, parse_policy
from gateway.reasons import REASONS
from tests.gateway_helpers import make_principal

pytestmark = pytest.mark.unit

TOP_K_AT_MOST_3 = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 3}},
    "additionalProperties": False,
}


def boundary(tool_arguments=None, tools="*"):
    doc = PolicyDocument(allowed_models="*", allowed_tools=tools, allowed_kbs="*", tool_arguments=tool_arguments or {})
    return build_boundary(make_principal(("agent",)), doc)


def call(arguments, tool="retrieve_chunks"):
    return Action(ActionKind.TOOL_CALL, tool, arguments=arguments)


async def verdict(b, action):
    return await PythonPolicyEngine().evaluate(b, action)


async def test_arguments_that_fit_the_schema_are_allowed():
    b = boundary({"retrieve_chunks": TOP_K_AT_MOST_3})
    assert (await verdict(b, call({"query": "breach", "top_k": 3}))).allowed


@pytest.mark.parametrize("arguments", [
    {"query": "breach", "top_k": 4},        # over the maximum
    {"query": "breach", "top_k": "3"},      # wrong type
    {"query": "breach", "namespace": "x"},  # an argument the schema does not list
    {"query": 5},
])
async def test_arguments_that_do_not_fit_are_denied_with_the_new_reason(arguments):
    result = await verdict(boundary({"retrieve_chunks": TOP_K_AT_MOST_3}), call(arguments))
    assert (result.allowed, result.reason) == (False, "tool_argument_not_allowed")


async def test_a_call_that_states_no_arguments_is_checked_as_an_empty_object_so_it_fails_closed():
    required = {"type": "object", "required": ["query"]}
    b = boundary({"retrieve_chunks": required})
    assert (await verdict(b, call(None))).reason == "tool_argument_not_allowed"
    assert (await verdict(b, call({}))).reason == "tool_argument_not_allowed"
    assert (await verdict(b, call({"query": "x"}))).allowed


async def test_a_tool_without_a_schema_is_not_checked_and_the_tool_allow_list_still_comes_first():
    b = boundary({"retrieve_chunks": TOP_K_AT_MOST_3}, tools=["retrieve_chunks", "list_namespaces"])
    assert (await verdict(b, call({"anything": [1, 2]}, tool="list_namespaces"))).allowed
    assert (await verdict(b, call({"query": "x", "top_k": 9}, tool="other"))).reason == "tool_not_allowed"


async def test_only_tool_calls_are_checked():
    b = boundary({"retrieve_chunks": {"type": "object", "maxProperties": 0}})
    assert (await verdict(b, Action(ActionKind.KB_READ, "legal", arguments={"x": 1}))).allowed


async def test_the_schema_rules_of_json_schema_apply_not_only_types():
    schema = {"type": "object", "properties": {"namespace": {"enum": ["legal", "kyc_aml"]}}, "required": ["namespace"]}
    b = boundary({"retrieve_chunks": schema})
    assert (await verdict(b, call({"namespace": "legal"}))).allowed
    assert (await verdict(b, call({"namespace": "default"}))).reason == "tool_argument_not_allowed"


# ---------------------------------------------------------------------------------------------- the document

def test_a_policy_with_valid_schemas_round_trips_through_json():
    doc = parse_policy({"allowed_tools": "*", "tool_arguments": {"retrieve_chunks": TOP_K_AT_MOST_3}})
    assert doc.tool_arguments == {"retrieve_chunks": TOP_K_AT_MOST_3}
    assert parse_policy(json.dumps(doc.model_dump())) == doc


@pytest.mark.parametrize("bad", [
    {"tool_arguments": {"retrieve_chunks": {"type": "no-such-type"}}},           # not a valid schema
    {"tool_arguments": {"retrieve_chunks": {"type": "object", "minProperties": -1}}},
    {"tool_arguments": {"": {"type": "object"}}},                                   # blank tool name
    {"tool_arguments": {"t": "not an object"}},
    {"tool_arguments": ["t"]},
    {"tool_arguments": {"t": {"$ref": "https://example.com/schema.json"}}},         # would be fetched from outside
    {"tool_arguments": {"t": {"properties": {"a": {"$ref": "file:///etc/passwd"}}}}},
    {"tool_arguments": {"t": {"$dynamicRef": "https://example.com/x"}}},
    {"tool_arguments": {"t": {"description": "x" * (MAX_TOOL_SCHEMA_BYTES + 1)}}},  # too big to read on every request
])
def test_a_bad_schema_is_refused_when_the_policy_is_read_or_published(bad):
    with pytest.raises(PolicyError):
        parse_policy(bad)


def test_a_schema_may_refer_to_itself():
    schema = {"type": "object", "properties": {"a": {"$ref": "#/$defs/n"}}, "$defs": {"n": {"type": "integer"}}}
    assert parse_policy({"tool_arguments": {"t": schema}}).tool_arguments["t"] == schema


def test_the_default_policy_and_an_old_document_have_no_schemas():
    assert parse_policy({"allowed_kbs": ["legal"]}).tool_arguments == {}


# ---------------------------------------------------------------------------------------------- boundary and catalogue

def test_the_boundary_carries_the_schemas_to_a_worker_and_back():
    b = boundary({"retrieve_chunks": TOP_K_AT_MOST_3})
    payload = json.loads(json.dumps(b.to_payload()))  # a job and a run token store it as JSON
    assert ExecutionBoundary.from_payload(payload).tool_arguments == {"retrieve_chunks": TOP_K_AT_MOST_3}
    del payload["tool_arguments"]  # a boundary written before Sprint 009
    assert ExecutionBoundary.from_payload(payload).tool_arguments == {}


def test_narrowing_keeps_the_schemas():
    b = boundary({"retrieve_chunks": TOP_K_AT_MOST_3})
    assert b.narrow(max_tool_calls=1).tool_arguments == b.tool_arguments


def test_the_arguments_are_never_shown_in_the_repr_of_an_action():
    assert "secret-value" not in repr(call({"query": "secret-value"}))


def test_the_new_reasons_are_in_the_catalogue_with_their_policy_field():
    info = REASONS["tool_argument_not_allowed"]
    assert (info.policy_field, info.stage) == ("tool_arguments", "policy")
    assert info.title and info.sentence.endswith(".")
    assert REASONS["run_token_scope"].policy_field is None
