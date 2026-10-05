"""Preview principal lookup: one more narrow SECURITY DEFINER function (Sprint 005, web edge).

A public-preview visitor gets a read-only session for the one principal named by PREVIEW_PRINCIPAL_ID. The
setting holds only the principal id, and the lookup runs before any tenant is known, so it uses the same
audited pattern as `auth_lookup_key` (0002) and `auth_lookup_principal` (0003): owner-owned, fixed
search_path, returns only what the session needs (tenant, kind, disabled flag and the scopes of the
principal's unrevoked keys). No secret or hash is returned. It creates no table and changes no data.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE OR REPLACE FUNCTION auth_lookup_preview(p_principal_id UUID)
RETURNS TABLE (principal_id UUID, tenant_id UUID, principal_kind TEXT, principal_disabled_at TIMESTAMPTZ, scopes TEXT[])
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT p.id, p.tenant_id, p.kind, p.disabled_at,
           COALESCE(
               (SELECT array_agg(DISTINCT s ORDER BY s)
                FROM api_keys k CROSS JOIN LATERAL unnest(k.scopes) AS s
                WHERE k.principal_id = p.id AND k.revoked_at IS NULL),
               '{}'::text[])
    FROM principals p
    WHERE p.id = p_principal_id
$$""",
    "REVOKE ALL ON FUNCTION auth_lookup_preview(UUID) FROM PUBLIC",
    """DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT EXECUTE ON FUNCTION auth_lookup_preview(UUID) TO gap_app;
    END IF;
END
$$""",
]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in STATEMENTS:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
