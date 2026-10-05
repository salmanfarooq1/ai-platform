"""Sprint 009 A5: an unauthorised tool argument gets a gateway deny row with reason `tool_argument_not_allowed`.

Real Postgres, the real `enforce()` and the real policy path: a policy is published with a schema, the context is built
from it, and the decision rows are read back as the owner. The arguments themselves are never stored."""
import json
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.identity.admin import admin_connection
from gateway import Action, ActionKind, build_context, enforce
from gateway.admin import set_policy
from tests.db_fixtures import principal_of
from tests.gateway_helpers import FakeRedis, make_runtime

pytestmark = pytest.mark.integration

SCHEMA_POLICY = {
    "allowed_kbs": "*", "allowed_models": "*", "allowed_tools": "*",
    "tool_arguments": {"retrieve_chunks": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "namespace": {"enum": ["legal"]}, "top_k": {"type": "integer", "minimum": 1, "maximum": 3}},
        "required": ["query"], "additionalProperties": False,
    }},
}


async def ctx_for(db_pool, database_url, tenant, policy=SCHEMA_POLICY):
    if policy is not None:
        with admin_connection(database_url) as conn:
            set_policy(conn, tenant.slug, policy, "tests")
    runtime = make_runtime(FakeRedis(), pool=db_pool)
    ctx = await build_context(runtime, principal_of(tenant, ("agent",)), "req-a5", "a" * 32)
    ctx.execution_id = uuid4()
    return ctx


def tool_call(**arguments):
    return Action(ActionKind.TOOL_CALL, "retrieve_chunks", input_text=arguments.get("query"), arguments=arguments)


async def rows(owner_pool, ctx):
    return await owner_pool.fetch("SELECT * FROM gateway_decisions WHERE execution_id = $1 ORDER BY created_at", ctx.execution_id)


async def test_a5_an_argument_the_policy_does_not_allow_is_denied_and_the_deny_row_names_the_reason(db_pool, owner_pool, database_url, tenant_a):
    ctx = await ctx_for(db_pool, database_url, tenant_a)
    decision = await enforce(ctx, tool_call(query="breach notice", namespace="legal", top_k=9))
    assert (decision.allowed, decision.stage, decision.reason) == (False, "policy", "tool_argument_not_allowed")
    assert decision.policy_version == 1
    [row] = await rows(owner_pool, ctx)
    assert (row["action"], row["resource"], row["outcome"], row["stage"], row["reason"]) == (
        "tool.call", "retrieve_chunks", "deny", "policy", "tool_argument_not_allowed")
    assert row["execution_id"] == ctx.execution_id and row["policy_version"] == 1
    assert row["row_hash"] is not None and row["chain_position"] is not None  # it is on the tenant's hash chain like any other


async def test_the_arguments_are_not_stored_anywhere_in_the_row(db_pool, owner_pool, database_url, tenant_a):
    ctx = await ctx_for(db_pool, database_url, tenant_a)
    await enforce(ctx, tool_call(query="needle-in-the-arguments", namespace="not-a-listed-namespace", top_k=1))
    [row] = await rows(owner_pool, ctx)
    assert "needle-in-the-arguments" not in json.dumps(dict(row), default=str)
    assert "not-a-listed-namespace" not in json.dumps(dict(row), default=str)
    assert row["input_hash"] and len(row["input_hash"]) == 64  # the hash of the input text, as for every call


async def test_arguments_that_fit_are_allowed_and_the_allow_row_says_so(db_pool, owner_pool, database_url, tenant_a):
    ctx = await ctx_for(db_pool, database_url, tenant_a)
    decision = await enforce(ctx, tool_call(query="breach notice", namespace="legal", top_k=3))
    assert decision.allowed and ctx.tool_calls == 1
    [row] = await rows(owner_pool, ctx)
    assert (row["outcome"], row["reason"]) == ("allow", "allowed")


async def test_a_denied_call_does_not_count_against_the_tool_call_limit(db_pool, database_url, tenant_a):
    ctx = await ctx_for(db_pool, database_url, tenant_a)
    await enforce(ctx, tool_call(query="x", top_k=99))
    assert ctx.tool_calls == 0 and [d.reason for d in ctx.denials] == ["tool_argument_not_allowed"]


async def test_another_tenants_policy_does_not_apply(db_pool, owner_pool, database_url, tenant_a, tenant_b):
    await ctx_for(db_pool, database_url, tenant_a)  # tenant A publishes the schema
    ctx_b = await ctx_for(db_pool, database_url, tenant_b, policy=None)  # tenant B has no policy: the platform default
    decision = await enforce(ctx_b, tool_call(query="x", top_k=99))
    assert decision.allowed


async def test_a_new_policy_version_replaces_the_schema_and_the_row_carries_the_new_version(db_pool, owner_pool, database_url, tenant_a):
    await ctx_for(db_pool, database_url, tenant_a)
    loose = {**SCHEMA_POLICY, "tool_arguments": {}}
    ctx = await ctx_for(db_pool, database_url, tenant_a, policy=loose)
    decision = await enforce(ctx, tool_call(query="x", top_k=99))
    assert decision.allowed and decision.policy_version == 2


@settings(max_examples=40, deadline=None)
@given(top_k=st.integers(-5, 50), namespace=st.sampled_from(["legal", "kyc_aml", "default", ""]))
def test_the_engine_agrees_with_the_schema_for_any_argument_pair(top_k, namespace):
    """Property: the verdict is allow exactly when jsonschema says the arguments fit (no second rule hides in the engine)."""
    import asyncio

    from jsonschema import Draft202012Validator

    from gateway import PolicyDocument, PythonPolicyEngine, build_boundary
    from tests.gateway_helpers import make_principal

    schema = SCHEMA_POLICY["tool_arguments"]["retrieve_chunks"]
    boundary = build_boundary(make_principal(("agent",)), PolicyDocument(allowed_models="*", allowed_tools="*", allowed_kbs="*", tool_arguments={"retrieve_chunks": schema}))
    arguments = {"query": "q", "namespace": namespace, "top_k": top_k}
    verdict = asyncio.run(PythonPolicyEngine().evaluate(boundary, tool_call(**arguments)))
    assert verdict.allowed == Draft202012Validator(schema).is_valid(arguments)


def test_m2_set_policy_refuses_a_tool_name_the_platform_does_not_have(database_url, tenant_a):
    from core.identity.admin import AdminError

    with admin_connection(database_url) as conn:
        with pytest.raises(AdminError, match="retreive_chunks"):
            set_policy(conn, tenant_a.slug, {"allowed_tools": "*", "tool_arguments": {"retreive_chunks": {"type": "object"}}}, "tests")
        assert set_policy(conn, tenant_a.slug, {"allowed_tools": "*", "tool_arguments": {"retrieve_chunks": {"type": "object"}, "search_documents": {"type": "object"}}}, "tests") == 1
