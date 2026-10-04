"""Startup guard: refuse to run as a role that bypasses row-level security (strict rules 2 and 14)."""
from asyncpg import Pool


class UnsafeDatabaseRoleError(RuntimeError):
    """DATABASE_URL connects as a superuser or a BYPASSRLS role."""


async def assert_rls_applies(pool: Pool) -> None:
    row = await pool.fetchrow("SELECT current_user AS name, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    if row is None:
        raise UnsafeDatabaseRoleError("could not read the connected role from pg_roles")
    if row["rolsuper"] or row["rolbypassrls"]:
        reason = "a superuser" if row["rolsuper"] else "a role with BYPASSRLS"
        raise UnsafeDatabaseRoleError(
            f"DATABASE_URL connects as role '{row['name']}', which is {reason}. Row-level security does not "
            "apply to it, so tenant isolation would not be enforced. Connect as a NOSUPERUSER NOBYPASSRLS "
            "role (the app role, gap_app) and put the owner role in MIGRATION_DATABASE_URL."
        )
