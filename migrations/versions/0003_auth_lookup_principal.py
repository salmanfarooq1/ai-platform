"""Principal lookup for JWT authentication: one more narrow SECURITY DEFINER function.

A verified JWT must name an existing, non-disabled principal that belongs to the tenant in the token
(strict rules 1 and 3). The check runs before the tenant is known, so it uses the same audited pattern
as `auth_lookup_key` (0002): owner-owned, fixed search_path, returns only what verification needs.
It returns a row only when BOTH the principal id and the tenant id match.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE OR REPLACE FUNCTION auth_lookup_principal(p_principal_id UUID, p_tenant_id UUID)
RETURNS TABLE (principal_id UUID, tenant_id UUID, principal_kind TEXT, principal_disabled_at TIMESTAMPTZ)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT p.id, p.tenant_id, p.kind, p.disabled_at
    FROM principals p
    WHERE p.id = p_principal_id AND p.tenant_id = p_tenant_id
$$""",
    "REVOKE ALL ON FUNCTION auth_lookup_principal(UUID, UUID) FROM PUBLIC",
    """DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT EXECUTE ON FUNCTION auth_lookup_principal(UUID, UUID) TO gap_app;
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
