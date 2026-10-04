"""ExecutionBoundary: immutable, built from scopes and policy, and it can only narrow."""
import dataclasses

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gateway.boundary import WILDCARD, BoundaryWidenError, ExecutionBoundary, build_boundary, deny_all_boundary
from gateway.policy import DEFAULT_POLICY, PolicyDocument
from tests.gateway_helpers import make_principal

NAMES = st.sampled_from(["legal", "kyc_aml", "default", "a", "b", "retrieve_chunks", "list_namespaces", "m1", "m2"])
RESOURCE_SETS = st.one_of(st.just(frozenset({WILDCARD})), st.frozensets(NAMES, max_size=6))
ACTIONS = st.frozensets(st.sampled_from(["kb.read", "kb.write", "model.invoke", "tool.call", "agent.run"]), max_size=5)


def within(child: frozenset[str], parent: frozenset[str]) -> bool:
    """The test's own oracle for 'is a subset', written independently of the implementation."""
    if WILDCARD in parent:
        return True
    return WILDCARD not in child and all(x in parent for x in child)


@st.composite
def boundaries(draw):
    return ExecutionBoundary(
        tenant_id=None, actions=draw(ACTIONS), kbs=draw(RESOURCE_SETS), tools=draw(RESOURCE_SETS), models=draw(RESOURCE_SETS),
        max_tool_calls=draw(st.integers(0, 50)), max_tokens=draw(st.integers(0, 100_000)),
        max_query_length=1000, blocked_terms=frozenset(),
    )


@settings(max_examples=300, deadline=None)
@given(parent=boundaries(), kbs=RESOURCE_SETS, tools=RESOURCE_SETS, models=RESOURCE_SETS, actions=ACTIONS,
       calls=st.integers(0, 60), tokens=st.integers(0, 120_000))
def test_narrow_result_is_always_a_subset_of_the_parent_or_raises(parent, kbs, tools, models, actions, calls, tokens):
    """Property: narrow() never returns a boundary wider than its parent; asking for more raises."""
    try:
        child = parent.narrow(kbs=kbs, tools=tools, models=models, actions=actions, max_tool_calls=calls, max_tokens=tokens)
    except BoundaryWidenError:
        widens = (not within(kbs, parent.kbs) or not within(tools, parent.tools) or not within(models, parent.models)
                  or not within(actions, parent.actions) or calls > parent.max_tool_calls or tokens > parent.max_tokens)
        assert widens, "raised although nothing was widened"
        return
    assert within(child.kbs, parent.kbs) and within(child.tools, parent.tools) and within(child.models, parent.models)
    assert within(child.actions, parent.actions)
    assert child.max_tool_calls <= parent.max_tool_calls and child.max_tokens <= parent.max_tokens
    assert (child.kbs, child.tools, child.models, child.actions) == (kbs, tools, models, actions)


@settings(max_examples=300, deadline=None)
@given(parent=boundaries(), extra=NAMES)
def test_widening_always_raises(parent, extra):
    """Property: adding a resource the parent lacks, or the wildcard under a concrete parent, raises."""
    if WILDCARD not in parent.kbs:
        if extra not in parent.kbs:
            with pytest.raises(BoundaryWidenError):
                parent.narrow(kbs=parent.kbs | {extra})
        with pytest.raises(BoundaryWidenError):
            parent.narrow(kbs={WILDCARD})
    with pytest.raises(BoundaryWidenError):
        parent.narrow(max_tool_calls=parent.max_tool_calls + 1)
    with pytest.raises(BoundaryWidenError):
        parent.narrow(max_tokens=parent.max_tokens + 1)


@settings(max_examples=300, deadline=None)
@given(boundaries(), RESOURCE_SETS)
def test_narrowing_twice_never_recovers_what_the_first_narrowing_dropped(parent, kbs):
    """Property: after narrowing, asking for the parent's resources again raises unless they fit the child."""
    try:
        first = parent.narrow(kbs=kbs)
    except BoundaryWidenError:
        return
    if within(parent.kbs, first.kbs):
        assert first.narrow(kbs=parent.kbs).kbs == parent.kbs  # nothing was dropped, so this is not a widening
    else:
        with pytest.raises(BoundaryWidenError):
            first.narrow(kbs=parent.kbs)


def test_a_boundary_is_frozen():
    boundary = build_boundary(make_principal(), None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(boundary, "max_tool_calls", 999)
    assert isinstance(boundary.kbs, frozenset) and isinstance(boundary.actions, frozenset)
    narrowed = boundary.narrow(kbs={"legal"})
    assert boundary.kbs == {WILDCARD} and narrowed.kbs == {"legal"}  # the parent is untouched


def test_the_default_boundary_is_what_scopes_grant_over_the_platform_defaults():
    boundary = build_boundary(make_principal(("query",)), None)
    assert boundary.actions == {"kb.read", "model.invoke", "tool.call", "feedback.write"}
    assert boundary.kbs == boundary.tools == boundary.models == {WILDCARD}
    assert boundary.max_tool_calls == DEFAULT_POLICY.max_tool_calls and boundary.policy_version is None
    assert boundary.visible_kbs() is None


def test_a_policy_narrows_resources_but_cannot_grant_actions_the_scopes_lack():
    policy = PolicyDocument(allowed_kbs=["legal"], allowed_tools=["retrieve_chunks"], allowed_models=["m1"], max_tool_calls=3,
                            max_tokens_per_request=500, max_query_length=200, blocked_terms=["Secret"])
    boundary = build_boundary(make_principal(("kb:read",)), policy, policy_version=7)
    # the policy lists models, but kb:read grants no model.invoke (tool.call is the MCP tool gate)
    assert boundary.actions == {"kb.read", "tool.call", "analytics.read"}
    assert (boundary.kbs, boundary.tools, boundary.models) == ({"legal"}, {"retrieve_chunks"}, {"m1"})
    assert (boundary.max_tool_calls, boundary.max_tokens, boundary.max_query_length) == (3, 500, 200)
    assert boundary.blocked_terms == {"secret"} and boundary.policy_version == 7
    assert boundary.visible_kbs() == ["legal"]
    assert boundary.allows_kb("legal") and not boundary.allows_kb("kyc_aml")


def test_unknown_scopes_grant_nothing_and_admin_grants_everything():
    assert build_boundary(make_principal(("root",)), None).actions == frozenset()
    assert build_boundary(make_principal(("admin",)), None).actions == {
        "kb.read", "kb.write", "model.invoke", "tool.call", "agent.run", "feedback.write", "analytics.read"}


def test_the_deny_all_boundary_allows_nothing():
    boundary = deny_all_boundary(None, "policy_unavailable")
    assert boundary.actions == frozenset() and boundary.max_tool_calls == 0
    assert not boundary.allows_kb("legal") and not boundary.allows_tool("x") and not boundary.allows_model("m")
