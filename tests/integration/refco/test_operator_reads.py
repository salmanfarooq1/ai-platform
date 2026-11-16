"""General operator reads verify credentials without exposing their stored hashes."""
import pytest

from core.identity import admin


@pytest.mark.parametrize("invalid", ["malformed", "wrong-secret", "revoked", "disabled"])
def test_operator_credential_inspection_fails_closed(database_url, tenant_a, invalid):
    token = tenant_a.tokens["full"]
    if invalid == "malformed":
        token = "invalid"
    elif invalid == "wrong-secret":
        token = token[:-1] + ("a" if token[-1] != "a" else "b")
    else:
        with admin.admin_connection(database_url) as conn, conn.cursor() as cur:
            if invalid == "revoked":
                admin.revoke_key(conn, tenant_a.prefixes["full"])
            else:
                cur.execute("UPDATE principals SET disabled_at = now() WHERE id = %s", (tenant_a.principal_id,))
    with admin.admin_connection(database_url) as conn, pytest.raises(admin.AdminError):
        admin.inspect_credential(conn, token)


def test_operator_reads_are_tenant_scoped_and_secret_free(database_url, tenants):
    first, second = tenants
    with admin.admin_connection(database_url) as conn:
        record = admin.inspect_credential(conn, first.tokens["full"])
        assert record["tenant_id"] == first.id
        assert record["tenant_slug"] == first.slug
        assert record["principal_id"] == first.principal_id
        assert set(record) == {"tenant_id", "tenant_slug", "principal_id", "principal_kind", "prefix", "scopes"}
        assert record["principal_kind"] == "service"
        assert record["prefix"] == first.prefixes["full"]
        assert set(record["scopes"]) == {"kb:read", "kb:write", "query", "agent"}
        assert not any("secret" in field or "hash" in field for field in record)
        keys = admin.list_keys(conn, first.slug, principal_id=first.principal_id)
        assert {k["prefix"] for k in keys} == set(first.prefixes.values())
        assert admin.list_keys(conn, first.slug, principal_id=second.principal_id) == []
        assert all("secret_hash" not in key and "token" not in key for key in keys)
        foreign = admin.inspect_credential(conn, second.tokens["full"])
        assert foreign["tenant_id"] == second.id != first.id
        assert foreign["principal_id"] == second.principal_id


def test_list_principals_is_tenant_scoped(database_url, tenants):
    first, second = tenants
    with admin.admin_connection(database_url) as conn:
        disabled = admin.create_principal(conn, first.slug, "user", "disabled-user")
        with conn.cursor() as cur:
            cur.execute("UPDATE principals SET disabled_at = now() WHERE id = %s", (str(disabled),))
        principals = admin.list_principals(conn, first.slug)
        assert {str(p["id"]) for p in principals} == {first.principal_id, str(disabled)}
        assert all(set(p) == {"id", "name", "kind", "disabled_at"} for p in principals)
        assert next(p for p in principals if str(p["id"]) == str(disabled))["disabled_at"] is not None
        assert [str(p["id"]) for p in admin.list_principals(conn, second.slug)] == [second.principal_id]
        with pytest.raises(admin.AdminError):
            admin.list_principals(conn, "unknown-tenant")


def test_list_kbs_is_tenant_scoped(database_url, tenants):
    first, second = tenants
    with admin.admin_connection(database_url) as conn:
        admin.create_kb(conn, second.slug, "foreign-only", "foreign description")
        rows = admin.list_kbs(conn, first.slug)
        assert [kb["slug"] for kb in rows] == ["default", "kyc_aml", "legal"]
        assert all(set(kb) == {"id", "slug", "description"} for kb in rows)
        assert "foreign-only" in {kb["slug"] for kb in admin.list_kbs(conn, second.slug)}
        with pytest.raises(admin.AdminError):
            admin.list_kbs(conn, "unknown-tenant")
