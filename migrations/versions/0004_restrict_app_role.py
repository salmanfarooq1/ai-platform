"""Least privilege for the app role: it only reads the identity tables.

0002 granted `gap_app` SELECT, INSERT, UPDATE and DELETE on every table (and as a default on future
tables). Row-level security keeps it inside its own tenant, but inside that tenant it could still edit
its own `api_keys` (scopes, revoked_at), `principals`, `tenants` and `knowledge_bases`. The app only reads
these; keys are created and revoked by the admin CLI (owner role) and `last_used_at` is written through the
SECURITY DEFINER function `auth_touch_key`. So write rights are removed here.

Default privileges are also removed: a future table gets no automatic grant to the app role, and the
migration that creates it must grant what it needs, explicitly.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

READ_ONLY = ("api_keys", "principals", "tenants", "knowledge_bases")

RESTRICT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON api_keys, principals, tenants, knowledge_bases FROM gap_app;
        REVOKE ALL ON alembic_version FROM gap_app;  -- the app has no business with migration state
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM gap_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM gap_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(RESTRICT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
