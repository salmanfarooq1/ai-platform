"""Trust baseline: the decision hash chain, retention, eval runs and the metrics reads (Sprint 008).

`gateway_decisions` gets `chain_position`, `prev_hash` and `row_hash` (all null for rows written before this
migration). `chain_heads` holds the last position and hash of each tenant, so a writer takes the next link under
an advisory lock. `chain_checkpoints` holds the hash at a position: the genesis checkpoint (position 0) and one per
purge, so the rows that remain after a purge still verify. `tenants.retention_days` is a per-tenant override of the
platform default (`DECISION_RETENTION_DAYS`, 90). `eval_runs` records each run of the eval gate. It belongs to no
tenant and the app role can only read it.

`gap_app` still has no UPDATE or DELETE on `gateway_decisions`. Retention runs through `decisions_purge_batch`, a
SECURITY DEFINER function with a pinned `search_path`, revoked from PUBLIC (the 0008 pattern). It refuses to run
for any tenant but the one in `app.tenant_id`, computes the cutoff itself (never earlier than 30 days), and in one
transaction writes the signed checkpoint and deletes. `gap_app` cannot insert into `chain_checkpoints`: only the purge function
does, and it refuses a checkpoint without a signature or one that is not what the database computes. `retention_due_tenants`, `trust_jobs_by_status` and `trust_outbox_lag`
are narrow reads for the scheduler and the metrics endpoint: tenant ids, counts and one age, never a row.

The functions run as the owner role. With FORCE the owner is subject to the policies too, so the tables the
functions touch get an `owner_access` policy that matches the owner role only. `gap_app` never matches it.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TENANT_SETTING = "nullif(current_setting('app.tenant_id', true), '')::uuid"

STATEMENTS = [
    "ALTER TABLE gateway_decisions ADD COLUMN IF NOT EXISTS chain_position BIGINT",
    "ALTER TABLE gateway_decisions ADD COLUMN IF NOT EXISTS prev_hash TEXT "
    "CHECK (prev_hash IS NULL OR length(prev_hash) = 64)",
    "ALTER TABLE gateway_decisions ADD COLUMN IF NOT EXISTS row_hash TEXT "
    "CHECK (row_hash IS NULL OR length(row_hash) = 64)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_gateway_decisions_chain ON gateway_decisions(tenant_id, chain_position) "
    "WHERE chain_position IS NOT NULL",
    "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS retention_days INTEGER CHECK (retention_days IS NULL OR retention_days >= 30)",
    """CREATE TABLE IF NOT EXISTS chain_heads (
    tenant_id  UUID PRIMARY KEY REFERENCES tenants(id),
    position   BIGINT NOT NULL CHECK (position >= 0),
    row_hash   TEXT NOT NULL CHECK (length(row_hash) = 64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    """CREATE TABLE IF NOT EXISTS chain_checkpoints (
    tenant_id  UUID NOT NULL REFERENCES tenants(id),
    position   BIGINT NOT NULL CHECK (position >= 0),
    row_hash   TEXT NOT NULL CHECK (length(row_hash) = 64),
    reason     TEXT NOT NULL CHECK (reason IN ('genesis', 'purge')),
    signature  TEXT,
    key_id     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (reason = 'genesis' OR (signature IS NOT NULL AND key_id IS NOT NULL)),
    PRIMARY KEY (tenant_id, position)
)""",
    """CREATE TABLE IF NOT EXISTS eval_runs (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suite    TEXT NOT NULL,
    scores   JSONB NOT NULL,
    baseline JSONB NOT NULL,
    passed   BOOLEAN NOT NULL,
    run_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_run_at ON eval_runs(run_at DESC)",
    # Every tenant that exists now gets a genesis checkpoint and a head at position 0. Rows written before this
    # migration stay unchained (null hashes); the chain starts with the first row written after it.
    """INSERT INTO chain_checkpoints (tenant_id, position, row_hash, reason)
SELECT id, 0, encode(sha256(convert_to('genesis:' || id::text, 'UTF8')), 'hex'), 'genesis' FROM tenants
ON CONFLICT DO NOTHING""",
    """INSERT INTO chain_heads (tenant_id, position, row_hash)
SELECT id, 0, encode(sha256(convert_to('genesis:' || id::text, 'UTF8')), 'hex') FROM tenants
ON CONFLICT DO NOTHING""",
]

RLS_TABLES = ("chain_heads", "chain_checkpoints")
OWNER_TABLES = ("gateway_decisions", "chain_heads", "chain_checkpoints", "jobs", "outbox")  # touched by the seed and the definer functions

OWNER_POLICY = """
DO $$
BEGIN
    DROP POLICY IF EXISTS owner_access ON {table};
    EXECUTE 'CREATE POLICY owner_access ON {table} TO ' || quote_ident(current_user) || ' USING (true) WITH CHECK (true)';
END
$$
"""

FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION decisions_purge_plan(p_tenant UUID, p_default_days INTEGER, p_limit INTEGER)
RETURNS TABLE (plan_days INTEGER, plan_position BIGINT, plan_hash TEXT)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_days       INTEGER;
    v_cutoff     TIMESTAMPTZ;
    v_first_live BIGINT;
    v_last_pos   BIGINT;
    v_last_hash  TEXT;
BEGIN
    -- Only the tenant the caller works as: a connection that has not set app.tenant_id, or set another, is refused.
    IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM nullif(current_setting('app.tenant_id', true), '')::uuid THEN
        RAISE EXCEPTION 'purge refused: the tenant is not the caller''s tenant';
    END IF;
    IF p_limit IS NULL OR p_limit < 1 THEN
        RAISE EXCEPTION 'purge refused: the batch size must be at least 1';
    END IF;
    -- A hard floor of 30 days, whatever the caller passes and whatever the tenant stored.
    SELECT GREATEST(COALESCE(t.retention_days, p_default_days, 30), 30) INTO v_days FROM tenants t WHERE t.id = p_tenant;
    IF v_days IS NULL THEN
        RAISE EXCEPTION 'purge refused: unknown tenant';
    END IF;
    v_cutoff := NOW() - make_interval(days => v_days);
    -- The oldest chained rows that are expired, up to the first row that is not: the chain stays contiguous.
    SELECT MIN(d.chain_position) INTO v_first_live FROM gateway_decisions d
    WHERE d.tenant_id = p_tenant AND d.chain_position IS NOT NULL AND d.created_at >= v_cutoff;
    SELECT MAX(c.chain_position) INTO v_last_pos FROM (
        SELECT d.chain_position FROM gateway_decisions d
        WHERE d.tenant_id = p_tenant AND d.chain_position IS NOT NULL
          AND (v_first_live IS NULL OR d.chain_position < v_first_live)
        ORDER BY d.chain_position LIMIT p_limit
    ) c;
    IF v_last_pos IS NOT NULL THEN
        SELECT d.row_hash INTO v_last_hash FROM gateway_decisions d
        WHERE d.tenant_id = p_tenant AND d.chain_position = v_last_pos;
    END IF;
    RETURN QUERY SELECT v_days, v_last_pos, v_last_hash;
END
$$""",
    """CREATE OR REPLACE FUNCTION decisions_purge_batch(
    p_tenant UUID, p_default_days INTEGER, p_limit INTEGER,
    p_expect_position BIGINT, p_expect_hash TEXT, p_signature TEXT, p_key_id TEXT)
RETURNS TABLE (purged INTEGER, checkpoint_position BIGINT, checkpoint_hash TEXT, retention_days INTEGER)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_days    INTEGER;
    v_pos     BIGINT;
    v_hash    TEXT;
    v_cutoff  TIMESTAMPTZ;
    v_chained INTEGER := 0;
    v_legacy  INTEGER := 0;
BEGIN
    -- The plan is computed here again (same transaction, same NOW()). The caller signed what it expected; a
    -- checkpoint is written only when that is exactly what the database finds, and only with a signature.
    SELECT p.plan_days, p.plan_position, p.plan_hash INTO v_days, v_pos, v_hash
    FROM decisions_purge_plan(p_tenant, p_default_days, p_limit) p;
    v_cutoff := NOW() - make_interval(days => v_days);
    IF v_pos IS NOT NULL THEN
        IF p_expect_position IS DISTINCT FROM v_pos OR p_expect_hash IS DISTINCT FROM v_hash THEN
            RAISE EXCEPTION 'purge refused: the signed checkpoint is not the one the database computes';
        END IF;
        IF p_signature IS NULL OR p_signature = '' OR p_key_id IS NULL OR p_key_id = '' THEN
            RAISE EXCEPTION 'purge refused: a checkpoint needs a signature';
        END IF;
        INSERT INTO chain_checkpoints (tenant_id, position, row_hash, reason, signature, key_id)
        VALUES (p_tenant, v_pos, v_hash, 'purge', p_signature, p_key_id)
        ON CONFLICT DO NOTHING;
        DELETE FROM gateway_decisions d WHERE d.tenant_id = p_tenant AND d.chain_position IS NOT NULL
          AND d.chain_position <= v_pos;
        GET DIAGNOSTICS v_chained = ROW_COUNT;
    END IF;
    -- Rows that were never chained (written before 0009, or a deny whose chain step failed) expire by age alone.
    DELETE FROM gateway_decisions d WHERE d.id IN (
        SELECT u.id FROM gateway_decisions u
        WHERE u.tenant_id = p_tenant AND u.chain_position IS NULL AND u.created_at < v_cutoff LIMIT p_limit
    );
    GET DIAGNOSTICS v_legacy = ROW_COUNT;
    RETURN QUERY SELECT v_chained + v_legacy, v_pos, v_hash, v_days;
END
$$""",
    """CREATE OR REPLACE FUNCTION retention_due_tenants(p_default_days INTEGER)
RETURNS TABLE (due_tenant UUID)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT t.id FROM tenants t
    WHERE EXISTS (
        SELECT 1 FROM gateway_decisions d
        WHERE d.tenant_id = t.id
          AND d.created_at < NOW() - make_interval(days => GREATEST(COALESCE(t.retention_days, p_default_days), 30))
    )
$$""",
    """CREATE OR REPLACE FUNCTION trust_jobs_by_status()
RETURNS TABLE (job_kind TEXT, job_status TEXT, job_count BIGINT)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT j.kind, j.status, COUNT(*) FROM jobs j GROUP BY j.kind, j.status
$$""",
    """CREATE OR REPLACE FUNCTION trust_outbox_lag()
RETURNS DOUBLE PRECISION
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MIN(o.created_at))), 0)::double precision
    FROM outbox o WHERE o.published_at IS NULL
$$""",
    "REVOKE ALL ON FUNCTION decisions_purge_plan(UUID, INTEGER, INTEGER) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION decisions_purge_batch(UUID, INTEGER, INTEGER, BIGINT, TEXT, TEXT, TEXT) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION retention_due_tenants(INTEGER) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION trust_jobs_by_status() FROM PUBLIC",
    "REVOKE ALL ON FUNCTION trust_outbox_lag() FROM PUBLIC",
]

GRANT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT SELECT, INSERT, UPDATE ON chain_heads TO gap_app;
        GRANT SELECT ON chain_checkpoints TO gap_app;  -- checkpoints are written only by decisions_purge_batch
        GRANT SELECT ON eval_runs TO gap_app;
        GRANT EXECUTE ON FUNCTION decisions_purge_plan(UUID, INTEGER, INTEGER) TO gap_app;
        GRANT EXECUTE ON FUNCTION decisions_purge_batch(UUID, INTEGER, INTEGER, BIGINT, TEXT, TEXT, TEXT) TO gap_app;
        GRANT EXECUTE ON FUNCTION retention_due_tenants(INTEGER) TO gap_app;
        GRANT EXECUTE ON FUNCTION trust_jobs_by_status() TO gap_app;
        GRANT EXECUTE ON FUNCTION trust_outbox_lag() TO gap_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    # The tables first, then the policies, then the seed rows: with FORCE the owner needs its policy to insert.
    for statement in STATEMENTS[:-2]:
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
    for statement in STATEMENTS[-2:]:
        bind.exec_driver_sql(statement)
    for statement in FUNCTIONS:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(GRANT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
