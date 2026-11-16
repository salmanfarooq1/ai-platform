"""Public policy publication and conflict semantics."""
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from core.identity.admin import AdminError
from gateway import admin


def connection(active, latest=4):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = [(uuid4(),), active, (latest + 1,)]
    return conn, cur


def test_policy_conflict_is_a_public_admin_error():
    assert issubclass(admin.PolicyConflict, AdminError)


@pytest.mark.parametrize("active, expected", [((4,), 3), (None, 4)])
def test_stale_policy_does_not_write(active, expected):
    conn, cur = connection(active)
    with pytest.raises(admin.PolicyConflict):
        admin.set_policy(conn, "tenant", {}, "operator", expected_version=expected)
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert any("FROM policies" in sql and "FOR UPDATE" in sql for sql in statements)
    assert not any(sql.startswith(("UPDATE", "INSERT")) for sql in statements)


@pytest.mark.parametrize("active, expected", [((4,), 4), (None, 0), ((4,), None)])
def test_publish_locks_tenant_and_active_head_before_allocating_version(active, expected):
    conn, cur = connection(active)
    assert admin.set_policy(conn, "tenant", {}, "operator", expected_version=expected) == 5
    statements = [call.args[0] for call in cur.execute.call_args_list]
    tenant_lock = next(i for i, sql in enumerate(statements) if "FROM tenants" in sql and "FOR UPDATE" in sql)
    head_lock = next(i for i, sql in enumerate(statements) if "FROM policies" in sql and "FOR UPDATE" in sql)
    allocation = next(i for i, sql in enumerate(statements) if "MAX(version)" in sql)
    assert tenant_lock < head_lock < allocation
