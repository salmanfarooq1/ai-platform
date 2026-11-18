#!/bin/sh
# Fresh local POC database: create `rag_platform` and the app login role `gap_app` if missing. Idempotent.
# Runs inside the Postgres container (stdin of `docker compose exec -T postgres sh -s`), where the compose
# environment already carries APP_DB_PASSWORD. The password is read from that environment inside psql (`\getenv`),
# so it appears in no process argument list; only this script travels over stdin.
# Schema migrations are applied afterwards as the owner role; the app role only gets the grants the migrations give.
set -eu
psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" <<'SQL'
\getenv pw APP_DB_PASSWORD
\if :{?pw}
\else
\set pw gap_app
\endif
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') AS missing \gset
\if :missing
CREATE ROLE gap_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'pw';
\endif
SELECT NOT EXISTS (SELECT FROM pg_database WHERE datname = 'rag_platform') AS missing_db \gset
\if :missing_db
CREATE DATABASE rag_platform;
\endif
SQL
echo "BOOTSTRAP_DONE"
