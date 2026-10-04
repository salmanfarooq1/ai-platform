"""Identity and tenancy: tenants, principals, API keys, knowledge bases, tenant_id and row-level security.

Existing rows are backfilled to one tenant, `default`, whose knowledge bases are the three
namespaces the platform shipped with. Backfill runs before RLS is enabled, because FORCE
applies to the table owner too. No login roles or passwords are created here; the app role
is environment setup. If a role named gap_app exists, the migration grants it DML (see scripts/admin/grant_app_role.sql
for a differently named role).

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
FORCED = ("documents", "document_registry", "usage_log", "feedback", "knowledge_bases")
# ENABLE only (no FORCE): the owner role must still be able to read these inside the audited
# SECURITY DEFINER lookup functions, before any tenant is known. The app role is always subject to RLS.
ENABLED_ONLY = ("principals", "api_keys")
TENANT_OWNED = FORCED + ENABLED_ONLY
TENANT_SETTING = "nullif(current_setting('app.tenant_id', true), '')::uuid"

STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS tenants (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)""",
    """CREATE TABLE IF NOT EXISTS principals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    kind        TEXT NOT NULL CHECK (kind IN ('user', 'service', 'agent')),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    disabled_at TIMESTAMPTZ
)""",
    """CREATE TABLE IF NOT EXISTS api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    principal_id UUID NOT NULL REFERENCES principals(id),
    prefix       TEXT NOT NULL UNIQUE,
    secret_hash  TEXT NOT NULL,
    scopes       TEXT[] NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ
)""",
    """CREATE TABLE IF NOT EXISTS knowledge_bases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    slug        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, slug)
)""",
    "CREATE INDEX IF NOT EXISTS idx_principals_tenant ON principals(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id)",
    # The default tenant and its knowledge bases (today's three namespaces).
    f"""INSERT INTO tenants (id, slug, name)
    VALUES ('{DEFAULT_TENANT_ID}', 'default', 'Default tenant')
    ON CONFLICT (slug) DO NOTHING""",
    f"""INSERT INTO knowledge_bases (tenant_id, slug, description) VALUES
    ('{DEFAULT_TENANT_ID}', 'legal', 'GDPR, CCPA, HIPAA, and other data protection regulations'),
    ('{DEFAULT_TENANT_ID}', 'kyc_aml', 'KYC, AML, and Bank Secrecy Act documentation'),
    ('{DEFAULT_TENANT_ID}', 'default', 'Uncategorized or general compliance documents')
    ON CONFLICT (tenant_id, slug) DO NOTHING""",
]

# (table, extra statements run after the column is NOT NULL)
_ADD_TENANT_COLUMN = [
    "ALTER TABLE {t} ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id)",
    f"UPDATE {{t}} SET tenant_id = '{DEFAULT_TENANT_ID}' WHERE tenant_id IS NULL",
    "ALTER TABLE {t} ALTER COLUMN tenant_id SET NOT NULL",
]

AFTER_COLUMNS = [
    # document_registry: the key becomes (tenant_id, namespace, document_id).
    "ALTER TABLE document_registry DROP CONSTRAINT IF EXISTS document_registry_pkey",
    "ALTER TABLE document_registry ADD PRIMARY KEY (tenant_id, namespace, document_id)",
    # Indexes lead with tenant_id. The HNSW and GIN indexes cannot, and stay as they are.
    "DROP INDEX IF EXISTS idx_documents_namespace",
    "DROP INDEX IF EXISTS idx_documents_ns_docid",
    "CREATE INDEX IF NOT EXISTS idx_documents_tenant_ns_docid ON documents(tenant_id, namespace, document_id)",
    "DROP INDEX IF EXISTS idx_usage_log_created",
    "DROP INDEX IF EXISTS idx_usage_log_endpoint_date",
    "CREATE INDEX IF NOT EXISTS idx_usage_log_tenant_created ON usage_log(tenant_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_usage_log_tenant_endpoint ON usage_log(tenant_id, endpoint, created_at)",
    "DROP INDEX IF EXISTS idx_feedback_created",
    "CREATE INDEX IF NOT EXISTS idx_feedback_tenant_created ON feedback(tenant_id, created_at DESC)",
]

# The one audited bypass: the key is looked up before the tenant is known. These two functions
# run as the migration (owner) role, return only what verification needs, and take no tenant.
AUTH_FUNCTIONS = [
    """CREATE OR REPLACE FUNCTION auth_lookup_key(p_prefix TEXT)
RETURNS TABLE (
    key_id UUID, tenant_id UUID, principal_id UUID, principal_kind TEXT,
    secret_hash TEXT, scopes TEXT[], revoked_at TIMESTAMPTZ, principal_disabled_at TIMESTAMPTZ
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT k.id, k.tenant_id, k.principal_id, p.kind, k.secret_hash, k.scopes, k.revoked_at, p.disabled_at
    FROM api_keys k JOIN principals p ON p.id = k.principal_id
    WHERE k.prefix = p_prefix
$$""",
    """CREATE OR REPLACE FUNCTION auth_touch_key(p_key_id UUID)
RETURNS VOID
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    UPDATE api_keys SET last_used_at = NOW() WHERE id = p_key_id
$$""",
    "REVOKE ALL ON FUNCTION auth_lookup_key(TEXT) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION auth_touch_key(UUID) FROM PUBLIC",
]


# Grants to the conventional app role, only when that role already exists (it is created by the
# environment, never here). A role with another name uses scripts/admin/grant_app_role.sql.
GRANT_IF_ROLE_EXISTS = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT USAGE ON SCHEMA public TO gap_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO gap_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gap_app;
        GRANT EXECUTE ON FUNCTION auth_lookup_key(TEXT) TO gap_app;
        GRANT EXECUTE ON FUNCTION auth_touch_key(UUID) TO gap_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO gap_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO gap_app;
    END IF;
END
$$
"""


def upgrade() -> None:
    bind = op.get_bind()
    for statement in STATEMENTS:
        bind.exec_driver_sql(statement)
    for table in ("documents", "document_registry", "usage_log", "feedback"):
        for template in _ADD_TENANT_COLUMN:
            bind.exec_driver_sql(template.format(t=table))
    for statement in AFTER_COLUMNS:
        bind.exec_driver_sql(statement)
    for statement in AUTH_FUNCTIONS:
        bind.exec_driver_sql(statement)

    # Row-level security. FORCE makes it apply to the table owner as well.
    for table in TENANT_OWNED:
        bind.exec_driver_sql(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        if table in FORCED:
            bind.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        bind.exec_driver_sql(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        bind.exec_driver_sql(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (tenant_id = {TENANT_SETTING}) WITH CHECK (tenant_id = {TENANT_SETTING})"
        )
    # A tenant can read only its own tenants row.
    bind.exec_driver_sql("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    bind.exec_driver_sql("DROP POLICY IF EXISTS tenant_isolation ON tenants")
    bind.exec_driver_sql(f"CREATE POLICY tenant_isolation ON tenants FOR SELECT USING (id = {TENANT_SETTING})")
    bind.exec_driver_sql(GRANT_IF_ROLE_EXISTS)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
