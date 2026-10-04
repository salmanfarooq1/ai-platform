#!/bin/bash
# Create the local database (if missing) in the compose Postgres, apply migrations as the owner role,
# and make sure the app login role `gap_app` exists and can use the tables.
# Usage: docker compose up -d postgres redis && scripts/setup_db.sh
set -euo pipefail
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
APP_DB_PASSWORD="${APP_DB_PASSWORD:-gap_app}"
docker exec "$CONTAINER" psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='rag_platform'" | grep -q 1 \
  || docker exec "$CONTAINER" psql -U postgres -c "CREATE DATABASE rag_platform"
# The role is created by docker/postgres-init on a fresh volume. On an older volume, create it now.
docker exec -i -e APP_DB_PASSWORD="$APP_DB_PASSWORD" "$CONTAINER" sh < docker/postgres-init/01-app-role.sh
# Migrations run as the owner role. The 0002 migration grants gap_app because the role already exists.
MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/rag_platform}" \
  poetry run alembic upgrade head
echo "SETUP_DONE"
