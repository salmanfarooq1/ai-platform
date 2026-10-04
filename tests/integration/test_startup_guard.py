"""The app refuses to run as a role that bypasses row-level security (requirement 4)."""
import secrets

import psycopg2
import pytest
from psycopg2 import sql

from core.database import pool as pool_module
from core.database.guard import UnsafeDatabaseRoleError
from tests import harness


@pytest.fixture
def point_pool_at(monkeypatch):
    def _set(dsn: str) -> None:
        monkeypatch.setitem(pool_module.DATABASE_CONFIG, "url", dsn)
        monkeypatch.setitem(pool_module.DATABASE_CONFIG, "pool_size", 2)

    return _set


async def test_superuser_connection_refuses_to_start_with_a_clear_message(database_url, point_pool_at):
    point_pool_at(database_url)  # connects as `postgres`, a superuser
    with pytest.raises(UnsafeDatabaseRoleError) as exc:
        await pool_module.create_pool()
    message = str(exc.value)
    assert "role 'postgres'" in message
    assert "superuser" in message
    assert "Row-level security does not apply" in message
    assert "NOSUPERUSER NOBYPASSRLS" in message
    assert "MIGRATION_DATABASE_URL" in message
    assert "postgres:postgres" not in message  # no credentials in the message


async def test_a_bypassrls_role_is_refused_too(database_url, point_pool_at):
    name = f"gap_bypass_{secrets.token_hex(3)}"
    admin = psycopg2.connect(harness.ADMIN_URL)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER BYPASSRLS PASSWORD 'pw'").format(sql.Identifier(name)))
    try:
        point_pool_at(database_url.replace("postgres:postgres", f"{name}:pw", 1))
        with pytest.raises(UnsafeDatabaseRoleError, match=f"role '{name}', which is a role with BYPASSRLS"):
            await pool_module.create_pool()
    finally:
        with admin.cursor() as cur:
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
        admin.close()


async def test_the_app_role_starts_and_the_pool_is_usable(app_database_url, point_pool_at):
    point_pool_at(app_database_url)
    pool = await pool_module.create_pool()
    try:
        assert await pool.fetchval("SELECT current_user") == "gap_app"
    finally:
        await pool.close()


async def test_a_refused_pool_is_closed_and_not_left_open(database_url, point_pool_at, monkeypatch):
    closed = []
    real_create = pool_module.asyncpg.create_pool

    class ClosingSpy:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        async def close(self):
            closed.append(True)
            await self._inner.close()

    async def spying_create(*args, **kwargs):
        return ClosingSpy(await real_create(*args, **kwargs))

    monkeypatch.setattr(pool_module.asyncpg, "create_pool", spying_create)
    point_pool_at(database_url)
    with pytest.raises(UnsafeDatabaseRoleError):
        await pool_module.create_pool()
    assert closed == [True]
