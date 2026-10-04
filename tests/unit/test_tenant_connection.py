"""tenant_connection sets app.tenant_id with a bound parameter inside a transaction."""
from uuid import UUID, uuid4

import pytest

from core.database.tenant import tenant_connection
from tests.fakes import FakePool


async def test_sets_the_tenant_first_with_a_bound_parameter_and_is_transaction_local():
    pool, tenant = FakePool(), uuid4()
    async with tenant_connection(pool, tenant) as conn:
        await conn.fetch("SELECT 1")
    first_sql, first_args = pool.conn.queries[0]
    assert first_sql == "SELECT set_config('app.tenant_id', $1, true)"  # is_local = true: SET LOCAL semantics
    assert first_args == (str(tenant),)
    assert pool.conn.queries[1][0] == "SELECT 1"


async def test_accepts_a_uuid_or_its_string_form():
    tenant = uuid4()
    for value in (tenant, str(tenant), str(tenant).upper()):
        pool = FakePool()
        async with tenant_connection(pool, value):
            pass
        assert pool.conn.queries[0][1] == (str(tenant),)


@pytest.mark.parametrize("bad", ["", "not-a-uuid", "1; DROP TABLE documents", "' OR 1=1 --", None, 5])
async def test_rejects_anything_that_is_not_a_uuid_before_touching_the_database(bad):
    pool = FakePool()
    with pytest.raises(ValueError):
        async with tenant_connection(pool, bad):  # type: ignore[arg-type]  # the invalid argument is the test
            pass
    assert pool.conn.queries == []


def test_uuid_type_is_what_principals_carry():
    assert isinstance(uuid4(), UUID)
