#!/bin/bash
# Strict rule 7: schema changes only through migrations.
# Fails if CREATE TABLE or ALTER TABLE appears in a .py or .sql file outside migrations/.
# Scanned: api/ core/ config.py tests/ scripts/ under the given root (default: repo root).
# Allowed (exact paths, relative to the root):
#   - tests/integration/fixtures/legacy_schema.sql: a frozen copy of the pre-Alembic schema,
#     used only to prove the baseline migration matches it.
#   - scripts/labs/: throwaway lab scripts, not shipped (see AGENTS.md).
# tests/harness.py only runs CREATE/DROP DATABASE and TRUNCATE, so it needs no exemption.
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"
hits=$(grep -rniE "CREATE[[:space:]]+TABLE|ALTER[[:space:]]+TABLE" \
  --include='*.py' --include='*.sql' \
  api core config.py tests scripts 2>/dev/null \
  | grep -v '^tests/integration/fixtures/legacy_schema\.sql:' \
  | grep -v '^scripts/labs/' || true)
if [ -n "$hits" ]; then
  echo "DDL found outside migrations/ (strict rule 7):"
  echo "$hits"
  exit 1
fi
echo "OK: no CREATE TABLE or ALTER TABLE outside migrations/"
