"""The metadata endpoint adds only its own read action to existing scopes."""
from uuid import UUID

import pytest

from core.identity.models import Principal
from gateway.boundary import build_boundary

pytestmark = pytest.mark.unit

PRE_012 = {
    "kb:read": {"kb.read", "tool.call", "analytics.read"},
    "kb:write": {"kb.write", "model.invoke"},
    "query": {"kb.read", "model.invoke", "tool.call", "feedback.write"},
    "agent": {"agent.run", "tool.call", "model.invoke", "kb.read"},
    "audit:read": {"audit.read"},
    "admin": {"kb.read", "kb.write", "model.invoke", "tool.call", "agent.run", "feedback.write", "analytics.read", "audit.read"},
}


@pytest.mark.parametrize("scope", ["kb:read", "kb:write", "query", "agent", "audit:read", "admin"])
def test_metadata_scope_grants_no_other_action(scope):
    principal = Principal(id=UUID("00000000-0000-0000-0000-000000000001"), tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
                          kind="user", scopes=frozenset({scope}))
    assert build_boundary(principal, None).actions == PRE_012[scope] | {"system.read"}
