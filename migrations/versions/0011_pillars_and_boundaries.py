"""Decision record versions, deployment shape probe and module-filtered job claims (Sprint 012).

The v1 columns remain the canonical signed record. New rows are written as v2 by the evidence sink.
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


DECISION_COLUMNS = (
    "ALTER TABLE gateway_decisions ADD COLUMN record_version SMALLINT NOT NULL DEFAULT 1 CHECK (record_version IN (1, 2))",
    "ALTER TABLE gateway_decisions ADD COLUMN extensions JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(extensions) = 'object')",
    "ALTER TABLE gateway_decisions ADD CONSTRAINT gateway_decisions_v1_extensions_empty CHECK (record_version <> 1 OR extensions = '{}'::jsonb)",
)

FUNCTIONS = (
    """CREATE OR REPLACE FUNCTION deploy_shape_has_multiple_tenants()
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
AS $$
    SELECT count(*) > 1 FROM public.tenants
$$""",
    "REVOKE ALL ON FUNCTION deploy_shape_has_multiple_tenants() FROM PUBLIC",
    # Replace the old unfiltered function with an overload that never expires or claims disabled work.
    """CREATE FUNCTION jobs_claim(p_worker TEXT, p_lease_seconds INTEGER, p_allowed_kinds TEXT[])
RETURNS TABLE (claimed_id UUID, claimed_tenant UUID)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
BEGIN
    IF p_allowed_kinds IS NULL OR cardinality(p_allowed_kinds) = 0 THEN
        RETURN;
    END IF;
    UPDATE public.jobs j SET status = 'failed', error_code = 'stopped', lease_until = NULL, locked_by = NULL,
           finished_at = NOW(), updated_at = NOW(), payload = j.payload - 'input'
    WHERE j.kind = ANY(p_allowed_kinds) AND j.status = 'running' AND j.lease_until < NOW() AND j.cancel_requested;
    UPDATE public.jobs j SET status = 'dead', error_code = 'lease_expired', lease_until = NULL, locked_by = NULL,
           finished_at = NOW(), updated_at = NOW(), payload = j.payload - 'input'
    WHERE j.kind = ANY(p_allowed_kinds) AND j.status = 'running' AND j.lease_until < NOW() AND j.attempts >= j.max_attempts;
    RETURN QUERY
    UPDATE public.jobs j SET status = 'running', lease_until = NOW() + make_interval(secs => p_lease_seconds),
           locked_by = p_worker, attempts = j.attempts + 1, started_at = COALESCE(j.started_at, NOW()),
           updated_at = NOW()
    WHERE j.id = (
        SELECT c.id FROM public.jobs c
        WHERE c.kind = ANY(p_allowed_kinds)
          AND ((c.status = 'queued' AND c.run_after <= NOW())
               OR (c.status = 'running' AND c.lease_until < NOW()))
        ORDER BY c.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING j.id, j.tenant_id;
END
$$""",
    "REVOKE ALL ON FUNCTION jobs_claim(TEXT, INTEGER) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION jobs_claim(TEXT, INTEGER, TEXT[]) FROM PUBLIC",
)

GRANTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        EXECUTE 'REVOKE ALL ON FUNCTION jobs_claim(TEXT, INTEGER) FROM gap_app';
        GRANT EXECUTE ON FUNCTION deploy_shape_has_multiple_tenants() TO gap_app;
        GRANT EXECUTE ON FUNCTION jobs_claim(TEXT, INTEGER, TEXT[]) TO gap_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    for statement in DECISION_COLUMNS:
        bind.exec_driver_sql(statement)
    for statement in FUNCTIONS:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(GRANTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
