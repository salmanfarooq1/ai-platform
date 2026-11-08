#!/usr/bin/env bash
# A base-image change can invalidate text indexes even within one Postgres major.
# Collation drift can only appear when the runtime libraries change, and that always recreates the container.
# So the full per-database scan runs once per container and runtime version; later checks stay cheap and bounded.
set -euo pipefail
user=${POSTGRES_USER:-postgres}
marker=/tmp/platform-collation-checked
pg_isready -q -U "$user"
query() { psql -X -v ON_ERROR_STOP=1 -U "$user" -d "$1" -Atqc "$2"; }
drift=$(query postgres "SELECT count(*) FROM pg_database WHERE datallowconn AND datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid)")
if [[ "$drift" != 0 ]]; then
  echo 'Database collation version differs from the runtime. See docs/postgres-upgrade.md.' >&2
  exit 1
fi
runtime=$(query postgres "SELECT pg_database_collation_actual_version(oid) FROM pg_database WHERE datname = 'template1'")
if [[ -f "$marker" && "$(cat "$marker")" == "$runtime" ]]; then
  exit 0
fi
databases=$(query postgres 'SELECT datname FROM pg_database WHERE datallowconn')
while IFS= read -r database; do
  drift=$(query "$database" "SELECT count(*) FROM pg_collation WHERE collversion IS NOT NULL AND collversion IS DISTINCT FROM pg_collation_actual_version(oid)")
  if [[ "$drift" != 0 ]]; then
    echo 'An installed collation differs from the runtime. See docs/postgres-upgrade.md.' >&2
    exit 1
  fi
done <<< "$databases"
printf '%s' "$runtime" > "$marker"
