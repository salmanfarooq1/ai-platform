"""Deployment shape is enforced by the database probe and tenant creation path."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.database.tenant import tenant_connection
from core.identity.admin import AdminError, admin_connection, create_tenant
from tests.fakes import fake_embedding

pytestmark = pytest.mark.integration


async def test_single_tenant_startup_refuses_two_tenants(db_pool, tenants):
    from core.identity.deploy_shape import assert_deploy_shape

    with pytest.raises(RuntimeError, match="DEPLOY_SHAPE"):
        await assert_deploy_shape(db_pool, "single_tenant")
    await assert_deploy_shape(db_pool, "multi_tenant")


async def test_concurrent_second_tenant_creation_is_refused(database_url, clean_state, owner_pool):
    def create(slug):
        try:
            with admin_connection(database_url) as conn:
                create_tenant(conn, slug, default_kb=False, deploy_shape="single_tenant")
            return True
        except AdminError:
            return False

    create("initial")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, ("second-a", "second-b")))
    assert outcomes == [False, False]
    assert await owner_pool.fetchval("SELECT count(*) FROM tenants") == 1

    await owner_pool.execute("TRUNCATE tenants CASCADE")
    with ThreadPoolExecutor(max_workers=2) as pool:
        empty_outcomes = list(pool.map(create, ("empty-a", "empty-b")))
    assert sorted(empty_outcomes) == [False, True]


async def test_probe_grants_and_search_path(db_pool, owner_pool, tenants):
    proc = await owner_pool.fetchrow(
        "SELECT p.proconfig, p.proacl FROM pg_proc p WHERE p.oid = 'deploy_shape_has_multiple_tenants()'::regprocedure"
    )
    assert "search_path=pg_catalog, public, pg_temp" in proc["proconfig"]
    assert await db_pool.fetchval("SELECT has_function_privilege('gap_app', 'deploy_shape_has_multiple_tenants()', 'EXECUTE')")
    assert not await owner_pool.fetchval(
        "SELECT EXISTS (SELECT 1 FROM aclexplode(proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE') "
        "FROM pg_proc WHERE oid = 'deploy_shape_has_multiple_tenants()'::regprocedure"
    )
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("CREATE TEMP TABLE tenants (id integer)")
            await conn.execute("INSERT INTO pg_temp.tenants SELECT generate_series(1, 5)")
            assert await conn.fetchval("SELECT deploy_shape_has_multiple_tenants()") is True


@pytest.mark.parametrize("deploy_shape", ["single_tenant", "multi_tenant"])
async def test_rls_present_in_both_shapes(db_pool, owner_pool, tenants, deploy_shape):
    # The pool is always the non-bypass app role; changing the asserted shape cannot widen tenant visibility.
    from uuid import UUID
    tenant_a, tenant_b = tenants
    for tenant in (tenant_a, tenant_b):
        await owner_pool.execute(
            "INSERT INTO documents (tenant_id, document_id, namespace, content, embedding, embedding_model, embedding_dim) "
            "VALUES ($1, 'shape.md', 'legal', 'shape data', $2, 'test/model', 768)",
            UUID(tenant.id), fake_embedding("shape"),
        )
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        documents = await conn.fetch("SELECT tenant_id FROM documents")
        decisions = await conn.fetch("SELECT tenant_id FROM gateway_decisions")
    assert all(str(row["tenant_id"]) == tenant_a.id for row in documents + decisions)
    assert all(str(row["tenant_id"]) != tenant_b.id for row in documents + decisions)
