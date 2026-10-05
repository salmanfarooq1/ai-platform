"""Helpers for the integration and e2e tiers: a throwaway Postgres database, and a
safe-to-clean Redis. If Postgres or Redis is unreachable the tier is skipped with a
clear reason (never passed silently).

Redis note: the platform's semantic cache uses a RediSearch index, and RediSearch can
only create indexes in database 0. So tests use database 0 and delete only the keys the
platform itself writes (rl:, budget:, cache:, semcache:). If database 0 holds any other
key, the tests refuse to touch it and skip, so a developer's real data is never removed.
"""
import os
import secrets
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg2
import pytest
import redis as redis_sync
from alembic import command
from alembic.config import Config

ADMIN_URL = os.getenv("TEST_DATABASE_ADMIN_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/0")
APP_ROLE = "gap_app"
APP_PASSWORD = os.getenv("APP_DB_PASSWORD", "gap_app")
PLATFORM_REDIS_PREFIXES = ("rl:", "budget:", "cost:", "cache:", "semcache:", "websess:")
ROOT = Path(__file__).resolve().parent.parent


def _replace_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


def app_url(owner_dsn: str) -> str:
    """The same database, reached as the non-privileged app role (row-level security applies to it)."""
    parts = urlsplit(owner_dsn)
    host = parts.hostname or "localhost"
    netloc = f"{APP_ROLE}:{quote(APP_PASSWORD, safe='')}@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def ensure_app_role() -> None:
    """Create the app login role if the environment has not (compose does it on a fresh volume).

    Roles are cluster-wide, so this runs once against the admin database. It never creates a superuser.
    """
    conn = psycopg2.connect(ADMIN_URL)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
            if cur.fetchone() is None:
                cur.execute(
                    f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %s",
                    (APP_PASSWORD,),
                )
    finally:
        conn.close()


def alembic_config(dsn: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", dsn)
    return cfg


def migrate(dsn: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(dsn), revision)


def require_postgres() -> None:
    try:
        psycopg2.connect(ADMIN_URL, connect_timeout=3).close()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres is not reachable at {ADMIN_URL.rsplit('@', 1)[-1]}: {exc}", allow_module_level=False)


def require_redis() -> None:
    try:
        client = redis_sync.Redis.from_url(REDIS_URL, socket_connect_timeout=3)
        client.ping()
        foreign = [
            k for k in client.scan_iter(count=500)
            if not k.decode().startswith(PLATFORM_REDIS_PREFIXES)
        ]
        client.close()
    except redis_sync.RedisError as exc:
        pytest.skip(f"Redis is not reachable at {REDIS_URL}: {exc}")
    if foreign:
        pytest.skip(f"Redis db 0 holds {len(foreign)} non-platform key(s); refusing to clean it for tests.")


def create_database(prefix: str = "gap_test_") -> tuple[str, str]:
    """Create a fresh database. Returns (name, dsn)."""
    name = f"{prefix}{secrets.token_hex(4)}"
    conn = psycopg2.connect(ADMIN_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    conn.close()
    return name, _replace_db(ADMIN_URL, name)


def drop_database(name: str) -> None:
    conn = psycopg2.connect(ADMIN_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    conn.close()


def truncate_tables(dsn: str) -> None:
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("TRUNCATE documents, document_registry, usage_log, feedback, api_keys, principals, "
            "knowledge_bases, policies, gateway_decisions, jobs, outbox, processed_events, chain_heads, chain_checkpoints, "
            "eval_runs, tenants RESTART IDENTITY")
    conn.close()


def clean_redis() -> None:
    """Delete platform-owned keys and the semantic cache index."""
    client = redis_sync.Redis.from_url(REDIS_URL)
    try:
        client.execute_command("FT.DROPINDEX", "idx:semantic_cache")
    except redis_sync.ResponseError:
        pass  # index does not exist yet
    for key in client.scan_iter(count=500):
        if key.decode().startswith(PLATFORM_REDIS_PREFIXES):
            client.delete(key)
    client.close()
