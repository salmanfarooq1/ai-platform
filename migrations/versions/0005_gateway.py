"""Gateway: versioned tenant policies and the decision record.

`policies` is append-only: a new version is a new row, and the only allowed change to an existing row is
`active` going from true to false (triggers refuse every other UPDATE and every DELETE). A partial unique
index allows one active version per tenant. `gateway_decisions` holds one row per `enforce()` call; it
carries the SHA-256 of the input and never the text.

Both tables have row-level security, forced. The app role `gap_app` has no default privileges (0004), so the
grants are explicit: SELECT on `policies` (policies are written by the admin CLI as the owner role), and
SELECT and INSERT on `gateway_decisions` (no UPDATE or DELETE: the record is append-only).

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_SETTING = "nullif(current_setting('app.tenant_id', true), '')::uuid"

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS policies (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id  UUID NOT NULL REFERENCES tenants(id),
    version    INTEGER NOT NULL CHECK (version > 0),
    document   JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT NOT NULL,
    active     BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (tenant_id, version)
)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_one_active ON policies(tenant_id) WHERE active",
    """CREATE OR REPLACE FUNCTION policies_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'policies are append-only: versions cannot be deleted';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.version IS DISTINCT FROM OLD.version OR NEW.document IS DISTINCT FROM OLD.document
       OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
        RAISE EXCEPTION 'policies are append-only: only the active flag can change';
    END IF;
    IF NEW.active AND NOT OLD.active THEN
        RAISE EXCEPTION 'policies are append-only: a version cannot be re-activated, publish a new version';
    END IF;
    RETURN NEW;
END
$$""",
    "DROP TRIGGER IF EXISTS trg_policies_append_only ON policies",
    "CREATE TRIGGER trg_policies_append_only BEFORE UPDATE OR DELETE ON policies "
    "FOR EACH ROW EXECUTE FUNCTION policies_append_only()",
    """CREATE TABLE IF NOT EXISTS gateway_decisions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id),
    principal_id   UUID,
    request_id     TEXT NOT NULL,
    trace_id       TEXT NOT NULL,
    action         TEXT NOT NULL,
    resource       TEXT,
    outcome        TEXT NOT NULL CHECK (outcome IN ('allow', 'deny')),
    stage          TEXT NOT NULL,
    reason         TEXT NOT NULL,
    policy_version INTEGER,
    input_hash     TEXT CHECK (input_hash IS NULL OR length(input_hash) = 64),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_gateway_decisions_tenant_created ON gateway_decisions(tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_gateway_decisions_tenant_request ON gateway_decisions(tenant_id, request_id)",
]

RLS_TABLES = ("policies", "gateway_decisions")

GRANT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT SELECT ON policies TO gap_app;
        GRANT SELECT, INSERT ON gateway_decisions TO gap_app;
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
    bind.exec_driver_sql(GRANT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
