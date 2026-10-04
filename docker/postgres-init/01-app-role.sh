#!/bin/sh
# Local/compose only: create the non-privileged app login role `gap_app` (NOSUPERUSER NOBYPASSRLS).
# Runs once, on the first start of an empty data volume. Password: APP_DB_PASSWORD (local default gap_app).
# On an existing volume: docker exec -i -e APP_DB_PASSWORD=gap_app postgres sh < docker/postgres-init/01-app-role.sh
set -eu
psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" -v pw="${APP_DB_PASSWORD:-gap_app}" <<'SQL'
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') AS missing \gset
\if :missing
CREATE ROLE gap_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'pw';
\endif
SQL
