"""The admin CLI accepts the `audit:read` scope (Sprint 005, blueprint section 1) and the key authenticates with it."""
import re

from core.identity.store import authenticate_api_key
from scripts.admin.identity import main


async def test_create_key_accepts_audit_read_and_the_key_carries_it(database_url, db_pool, tenant_a, capsys):
    code = main(["--dsn", database_url, "create-key", tenant_a.principal_id, "--scopes", "audit:read"])
    out = capsys.readouterr().out
    assert code == 0 and "scopes=audit:read" in out
    token = re.search(r"KEY \(shown once, store it now\): (\S+)", out).group(1)
    principal = await authenticate_api_key(db_pool, token)
    assert principal is not None and principal.scopes == frozenset({"audit:read"})
    assert principal.has_scope("audit:read") and not principal.has_scope("kb:read")


async def test_create_key_still_refuses_an_unknown_scope(database_url, tenant_a, capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["--dsn", database_url, "create-key", tenant_a.principal_id, "--scopes", "audit:write"])
    capsys.readouterr()
