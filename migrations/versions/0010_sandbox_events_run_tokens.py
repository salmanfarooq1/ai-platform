"""Sandboxed agent runs: the sandbox event log and the run tokens (Sprint 009).

`sandbox_events` holds what the sandbox reported for a run: a start, an exit, a denied network call, a denied
file access, a limit that was hit, a log line. It is keyed by `execution_id`, so the runs API can merge it with
the `gateway_decisions` of the same run. `detail` is a small JSON object with no secret and no input text; the
adapter truncates it, and a CHECK refuses more than 2 KiB. The table is append-only for the app role (SELECT and
INSERT, no UPDATE or DELETE). Retention of this table is an open question (Q35).

`run_tokens` (with `key_id`, the API key that started the run, so revoking that key ends the token) holds the short-lived credential a sandboxed agent uses to call the gateway. It is bound to one
`execution_id` and one principal, and carries the boundary the run was accepted with, so the gateway enforces the
same boundary for every call of the run. Only the SHA-256 of the secret is stored (never the token), the token
expires, and it can be revoked. The prefix is public and indexes the lookup, as with API keys (0002).

The token is verified before the tenant is known, so the lookup is one more narrow SECURITY DEFINER function in the
pattern of `auth_lookup_key` (0002): owner-owned, fixed search_path, revoked from PUBLIC, returning only what
verification needs. With FORCE the owner is subject to the policies too, so `run_tokens` gets an `owner_access`
policy for the owner role only. `gap_app` never matches it. A table added by a migration needs an explicit grant.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TENANT_SETTING = "nullif(current_setting('app.tenant_id', true), '')::uuid"

SANDBOX_EVENT_KINDS = ("start", "exit", "network_denied", "file_denied", "limit_hit", "log")

STATEMENTS = [
    # A foreign key check is not subject to row-level security, so a plain REFERENCES principals(id) would let one tenant
    # point a token at another tenant's principal. The pair (id, tenant_id) closes that.
    "ALTER TABLE principals ADD CONSTRAINT principals_id_tenant_key UNIQUE (id, tenant_id)",
    f"""CREATE TABLE IF NOT EXISTS sandbox_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seq          BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    execution_id UUID NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ({", ".join(repr(k) for k in SANDBOX_EVENT_KINDS)})),
    detail       JSONB NOT NULL DEFAULT '{{}}'::jsonb CHECK (octet_length(detail::text) <= 2048),
    at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_sandbox_events_run ON sandbox_events(tenant_id, execution_id, at, seq)",
    """CREATE TABLE IF NOT EXISTS run_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    execution_id UUID NOT NULL,
    principal_id UUID NOT NULL,
    key_id       UUID,
    prefix       TEXT NOT NULL UNIQUE CHECK (length(prefix) = 8),
    secret_hash  TEXT NOT NULL CHECK (length(secret_hash) = 64),
    scopes       TEXT[] NOT NULL,
    boundary     JSONB NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (principal_id, tenant_id) REFERENCES principals (id, tenant_id)
)""",
    "CREATE INDEX IF NOT EXISTS idx_run_tokens_run ON run_tokens(tenant_id, execution_id)",
]

RLS_TABLES = ("sandbox_events", "run_tokens")

OWNER_POLICY = """
DO $$
BEGIN
    DROP POLICY IF EXISTS owner_access ON run_tokens;
    EXECUTE 'CREATE POLICY owner_access ON run_tokens TO ' || quote_ident(current_user) || ' USING (true) WITH CHECK (true)';
END
$$
"""

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION auth_lookup_run_token(p_prefix TEXT)
RETURNS TABLE (
    token_id UUID, tenant_id UUID, execution_id UUID, principal_id UUID, principal_kind TEXT,
    secret_hash TEXT, scopes TEXT[], boundary JSONB, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ,
    principal_disabled_at TIMESTAMPTZ, db_now TIMESTAMPTZ, key_revoked_at TIMESTAMPTZ
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT t.id, t.tenant_id, t.execution_id, t.principal_id, p.kind, t.secret_hash, t.scopes, t.boundary,
           t.expires_at, t.revoked_at, p.disabled_at, NOW(), k.revoked_at
    FROM run_tokens t JOIN principals p ON p.id = t.principal_id LEFT JOIN api_keys k ON k.id = t.key_id
    WHERE t.prefix = p_prefix
$$""",
    "REVOKE ALL ON FUNCTION auth_lookup_run_token(TEXT) FROM PUBLIC",
]

GRANT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT SELECT, INSERT ON sandbox_events TO gap_app;       -- append-only for the app role
        GRANT SELECT, INSERT, UPDATE ON run_tokens TO gap_app;   -- UPDATE revokes a token; there is no DELETE
        GRANT EXECUTE ON FUNCTION auth_lookup_run_token(TEXT) TO gap_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    for statement in STATEMENTS:
        bind.exec_driver_sql(statement)
    for table in RLS_TABLES:
        bind.exec_driver_sql(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        bind.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        bind.exec_driver_sql(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        bind.exec_driver_sql(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = {TENANT_SETTING}) WITH CHECK (tenant_id = {TENANT_SETTING})"
        )
    bind.exec_driver_sql(OWNER_POLICY)
    for statement in FUNCTIONS:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(GRANT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
