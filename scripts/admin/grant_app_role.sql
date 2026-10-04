-- Grants for a non-privileged app role whose name is not `gap_app`. Idempotent. Run as the owner role,
-- after migrations. (For `gap_app` itself, migrations 0002 and 0004 do this.)
-- Usage: psql "$MIGRATION_DATABASE_URL" -v app_role=myrole -f scripts/admin/grant_app_role.sql
-- The role is created by the environment (LOGIN NOSUPERUSER NOBYPASSRLS, password from a secret).
-- Least privilege: the app reads the identity tables and writes only the data tables. Keys are managed
-- by the admin CLI (owner role); last_used_at goes through auth_touch_key.
GRANT USAGE ON SCHEMA public TO :"app_role";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT INSERT, UPDATE, DELETE ON documents, document_registry, usage_log, feedback TO :"app_role";
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON api_keys, principals, tenants, knowledge_bases FROM :"app_role";
REVOKE ALL ON alembic_version FROM :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";
GRANT EXECUTE ON FUNCTION auth_lookup_key(TEXT) TO :"app_role";
GRANT EXECUTE ON FUNCTION auth_touch_key(UUID) TO :"app_role";
GRANT EXECUTE ON FUNCTION auth_lookup_principal(UUID, UUID) TO :"app_role";
