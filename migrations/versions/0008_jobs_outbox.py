"""Durable jobs, the transactional outbox and consumer dedupe (Sprint 007).

`jobs` is the work queue. A worker claims a job with `SELECT ... FOR UPDATE SKIP LOCKED`, holds it under a
lease, and a job whose lease ran out is claimed again. `outbox` holds the CloudEvents a transaction produced,
written in the same transaction as the state change, for a relay to publish at least once. `processed_events`
lets a durable consumer skip an event it already handled (dedupe by CloudEvent id).

All three tables have row-level security, forced, with the usual tenant policy. `gap_app` gets SELECT, INSERT
and UPDATE (no DELETE: retention is Sprint 008) and nothing else. A table added by a migration needs an
explicit grant, because 0004 removed the default privileges.

Workers and the relay do not belong to a tenant, so they cannot read these tables before they know whose
rows to open. Three narrow SECURITY DEFINER functions, in the pattern of `auth_lookup_key` (0002), do that
one step and nothing else:
- `jobs_claim(worker, lease_seconds)` claims one job and returns only its id and its tenant. It also ends the
  jobs whose lease ran out after their last attempt (`dead`) and the ones somebody asked to stop (`failed`,
  `stopped`) instead of running them again. Everything else the worker does happens under `tenant_connection`.
- `jobs_tenant_of_execution(execution_id)` returns the tenant of an agent run, so a caller that holds only the
  run id can open the row under that tenant. It returns one uuid.
- `outbox_pending(limit, max_attempts)` lists the ids and tenants of events not yet published.

The functions run as the owner role. With FORCE the owner is subject to the policies too (a superuser is not),
so the tables get one more policy that applies to the owner role only. `gap_app` never matches it.

`jobs.namespace` (the knowledge base a job belongs to) and `jobs.principal_id` (who started it) are columns, not payload
fields, so the routes can limit what a caller sees to the knowledge bases its boundary allows and, for agent runs,
to its own runs.

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

TENANT_SETTING = "nullif(current_setting('app.tenant_id', true), '')::uuid"

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id),
    kind             TEXT NOT NULL CHECK (kind <> ''),
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'dead')),
    payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key  TEXT,
    attempts         INTEGER NOT NULL DEFAULT 0,
    max_attempts     INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    run_after        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_until      TIMESTAMPTZ,
    locked_by        TEXT,
    progress_done    INTEGER NOT NULL DEFAULT 0,
    progress_total   INTEGER NOT NULL DEFAULT 0,
    error_code       TEXT,
    error_detail     TEXT,
    resource         TEXT,
    principal_id     UUID,
    namespace        TEXT,
    execution_id     UUID,
    result           JSONB,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ
)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency ON jobs(tenant_id, idempotency_key) "
    "WHERE idempotency_key IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_execution ON jobs(execution_id) WHERE execution_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_jobs_claimable ON jobs(created_at) WHERE status IN ('queued', 'running')",
    "CREATE INDEX IF NOT EXISTS idx_jobs_tenant_created ON jobs(tenant_id, created_at DESC, id DESC)",
    """CREATE TABLE IF NOT EXISTS outbox (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    event_id     TEXT NOT NULL,
    event        JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    attempts     INTEGER NOT NULL DEFAULT 0
)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_outbox_event ON outbox(tenant_id, event_id)",
    "CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(created_at) WHERE published_at IS NULL",
    """CREATE TABLE IF NOT EXISTS processed_events (
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    consumer     TEXT NOT NULL,
    event_id     TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, consumer, event_id)
)""",
]

RLS_TABLES = ("jobs", "outbox", "processed_events")
OWNER_TABLES = ("jobs", "outbox")  # the tables the SECURITY DEFINER functions read before a tenant is known

OWNER_POLICY = """
DO $$
BEGIN
    DROP POLICY IF EXISTS owner_access ON {table};
    EXECUTE 'CREATE POLICY owner_access ON {table} TO ' || quote_ident(current_user) || ' USING (true) WITH CHECK (true)';
END
$$
"""

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION jobs_claim(p_worker TEXT, p_lease_seconds INTEGER)
RETURNS TABLE (claimed_id UUID, claimed_tenant UUID)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    -- A job nobody holds any more and somebody asked to stop is stopped, not run again.
    UPDATE jobs j SET status = 'failed', error_code = 'stopped', lease_until = NULL, locked_by = NULL,
           finished_at = NOW(), updated_at = NOW(), payload = j.payload - 'input'
    WHERE j.status = 'running' AND j.lease_until < NOW() AND j.cancel_requested;
    -- A job whose lease ran out after its last attempt is dead.
    UPDATE jobs j SET status = 'dead', error_code = 'lease_expired', lease_until = NULL, locked_by = NULL,
           finished_at = NOW(), updated_at = NOW(), payload = j.payload - 'input'
    WHERE j.status = 'running' AND j.lease_until < NOW() AND j.attempts >= j.max_attempts;
    RETURN QUERY
    UPDATE jobs j SET status = 'running', lease_until = NOW() + make_interval(secs => p_lease_seconds),
           locked_by = p_worker, attempts = j.attempts + 1, started_at = COALESCE(j.started_at, NOW()),
           updated_at = NOW()
    WHERE j.id = (
        SELECT c.id FROM jobs c
        WHERE (c.status = 'queued' AND c.run_after <= NOW())
           OR (c.status = 'running' AND c.lease_until < NOW())
        ORDER BY c.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING j.id, j.tenant_id;
END
$$""",
    """CREATE OR REPLACE FUNCTION jobs_tenant_of_execution(p_execution_id UUID)
RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT tenant_id FROM jobs WHERE execution_id = p_execution_id
$$""",
    """CREATE OR REPLACE FUNCTION outbox_pending(p_limit INTEGER, p_max_attempts INTEGER)
RETURNS TABLE (outbox_id UUID, outbox_tenant UUID)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT o.id, o.tenant_id FROM outbox o
    WHERE o.published_at IS NULL AND o.attempts < p_max_attempts
    ORDER BY o.created_at
    LIMIT p_limit
$$""",
    "REVOKE ALL ON FUNCTION jobs_claim(TEXT, INTEGER) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION jobs_tenant_of_execution(UUID) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION outbox_pending(INTEGER, INTEGER) FROM PUBLIC",
]

GRANT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT SELECT, INSERT, UPDATE ON jobs, outbox, processed_events TO gap_app;
        GRANT EXECUTE ON FUNCTION jobs_claim(TEXT, INTEGER) TO gap_app;
        GRANT EXECUTE ON FUNCTION jobs_tenant_of_execution(UUID) TO gap_app;
        GRANT EXECUTE ON FUNCTION outbox_pending(INTEGER, INTEGER) TO gap_app;
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
    for table in OWNER_TABLES:
        bind.exec_driver_sql(OWNER_POLICY.format(table=table))
    for statement in FUNCTIONS:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(GRANT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
