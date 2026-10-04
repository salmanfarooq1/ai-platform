"""API key lookup against real Postgres through the SECURITY DEFINER function (requirement 5)."""
from uuid import UUID

from core.identity.admin import admin_connection, create_key, create_principal, revoke_key
from core.identity.keys import generate_key, parse_key
from core.identity.store import authenticate_api_key


async def test_valid_key_returns_the_principal_with_tenant_kind_and_scopes(db_pool, tenant_a):
    principal = await authenticate_api_key(db_pool, tenant_a.tokens["full"])
    assert principal is not None
    assert principal.tenant_id == UUID(tenant_a.id)
    assert principal.id == UUID(tenant_a.principal_id)
    assert principal.kind == "service"
    assert principal.scopes == frozenset({"kb:read", "kb:write", "query", "agent"})


async def test_each_key_carries_its_own_scopes(db_pool, tenant_a):
    assert (await authenticate_api_key(db_pool, tenant_a.tokens["query_only"])).scopes == frozenset({"query"})
    assert (await authenticate_api_key(db_pool, tenant_a.tokens["reader"])).scopes == frozenset({"kb:read"})


async def test_keys_of_two_tenants_resolve_to_their_own_tenant(db_pool, tenants):
    a, b = tenants
    assert (await authenticate_api_key(db_pool, a.tokens["full"])).tenant_id == UUID(a.id)
    assert (await authenticate_api_key(db_pool, b.tokens["full"])).tenant_id == UUID(b.id)


async def test_wrong_secret_with_a_real_prefix_is_rejected(db_pool, tenant_a):
    prefix = tenant_a.prefixes["full"]
    forged = f"gap_{prefix}_" + "A" * 43
    assert parse_key(forged) is not None
    assert await authenticate_api_key(db_pool, forged) is None


async def test_unknown_prefix_is_rejected(db_pool, tenant_a):
    assert await authenticate_api_key(db_pool, generate_key().token) is None


async def test_malformed_tokens_are_rejected_without_a_database_call(tenant_a):
    class NoDatabase:
        async def fetchrow(self, *a):
            raise AssertionError("the database must not be queried for a malformed token")

    for token in ("", "garbage", "gap_short_secret", "Bearer x", tenant_a.tokens["full"] + "x" * 200):
        assert await authenticate_api_key(NoDatabase(), token) is None


async def test_revoked_key_is_rejected_immediately_and_others_keep_working(db_pool, database_url, tenant_a):
    assert await authenticate_api_key(db_pool, tenant_a.tokens["full"]) is not None
    with admin_connection(database_url) as conn:
        assert revoke_key(conn, tenant_a.prefixes["full"]) is True
    assert await authenticate_api_key(db_pool, tenant_a.tokens["full"]) is None
    assert await authenticate_api_key(db_pool, tenant_a.tokens["reader"]) is not None


async def test_key_of_a_disabled_principal_is_rejected(db_pool, owner_pool, tenant_a):
    await owner_pool.execute("UPDATE principals SET disabled_at = NOW() WHERE id = $1", UUID(tenant_a.principal_id))
    assert await authenticate_api_key(db_pool, tenant_a.tokens["full"]) is None


async def test_successful_authentication_records_last_used_at(db_pool, owner_pool, tenant_a):
    prefix = tenant_a.prefixes["full"]
    assert await owner_pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", prefix) is None
    await authenticate_api_key(db_pool, tenant_a.tokens["full"])
    assert await owner_pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", prefix) is not None
    # a failed attempt does not touch another key's timestamp
    assert await owner_pool.fetchval("SELECT last_used_at FROM api_keys WHERE prefix = $1", tenant_a.prefixes["reader"]) is None


async def test_only_the_hash_is_stored_never_the_secret(owner_pool, tenant_a):
    token = tenant_a.tokens["full"]
    secret = parse_key(token)[1]
    row = await owner_pool.fetchrow("SELECT * FROM api_keys WHERE prefix = $1", tenant_a.prefixes["full"])
    assert len(row["secret_hash"]) == 64 and row["secret_hash"] != secret
    stored_text = " ".join(str(v) for v in row.values())
    assert secret not in stored_text and token not in stored_text


async def test_the_lookup_function_is_the_only_cross_tenant_door_and_returns_no_plaintext(db_pool, tenants):
    """gap_app has no tenant set here and still resolves a key: that is the one audited bypass. It returns
    verification columns only."""
    a, _ = tenants
    row = await db_pool.fetchrow("SELECT * FROM auth_lookup_key($1)", a.prefixes["full"])
    assert set(row.keys()) == {"key_id", "tenant_id", "principal_id", "principal_kind", "secret_hash", "scopes",
                               "revoked_at", "principal_disabled_at"}
    assert await db_pool.fetchrow("SELECT * FROM auth_lookup_key($1)", "nonexist") is None


async def test_a_new_principal_and_key_in_the_same_tenant_work(db_pool, database_url, tenant_a):
    with admin_connection(database_url) as conn:
        pid = create_principal(conn, "tenant-a", "agent", "second")
        key = create_key(conn, pid, ["agent"])
    principal = await authenticate_api_key(db_pool, key.token)
    assert (principal.id, principal.tenant_id, principal.kind) == (pid, UUID(tenant_a.id), "agent")
    assert principal.scopes == frozenset({"agent"})


async def test_confirm_jwt_principal_accepts_only_an_existing_enabled_principal_of_that_tenant(db_pool, owner_pool, tenants):
    from uuid import uuid4

    from core.identity.models import Principal
    from core.identity.store import confirm_jwt_principal

    a, b = tenants

    def claim(principal, tenant, kind="user"):
        return Principal(id=UUID(principal), tenant_id=UUID(tenant), kind=kind, scopes=frozenset({"query"}))

    ok = await confirm_jwt_principal(db_pool, claim(a.principal_id, a.id))
    assert (ok.id, ok.tenant_id, ok.kind, ok.scopes) == (UUID(a.principal_id), UUID(a.id), "service", frozenset({"query"}))
    assert await confirm_jwt_principal(db_pool, claim(str(uuid4()), a.id)) is None            # unknown
    assert await confirm_jwt_principal(db_pool, claim(a.principal_id, b.id)) is None          # tenant mismatch
    assert await confirm_jwt_principal(db_pool, claim(b.principal_id, a.id)) is None          # tenant mismatch
    await owner_pool.execute("UPDATE principals SET disabled_at = NOW() WHERE id = $1", UUID(a.principal_id))
    assert await confirm_jwt_principal(db_pool, claim(a.principal_id, a.id)) is None          # disabled
    assert await confirm_jwt_principal(db_pool, claim(b.principal_id, b.id)) is not None      # others unaffected
