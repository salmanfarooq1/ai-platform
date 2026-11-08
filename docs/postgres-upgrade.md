# Postgres 16 image transition

The local stack uses pgvector 0.8.7 with Postgres 16 on Debian trixie. The image passes the fixed-critical security gate. Postgres stays on major 16. The previous bookworm image uses libc collation version 2.36; trixie uses 2.41. Text index order can change across that boundary.

Fresh installations use the new `pgdata_trixie` Compose volume. Existing `pgdata` is preserved and is not attached to the new image. Do not substitute the trixie image over the old volume. The healthcheck rejects database or explicit-collation version drift; changing a version label alone does not rebuild affected indexes.

## Existing installation

1. Keep the old deployment and its image digest available. Stop application and worker writes. Make a verified backup using the old Postgres 16 image, including application databases and required roles. Keep credentials outside captured logs.
2. Preserve the old `pgdata` volume and the backup. Initialize `pgdata_trixie` with the new image in an isolated maintenance deployment. Do not publish it through the application until verification passes.
3. Restore roles and use a logical dump/restore of the application database into the fresh database. Use the owner's migration credential. Logical restore rebuilds indexes using the new collation libraries. Do not use a physical data-directory copy or copy the old database's collation-version metadata into the new database.
4. Run the database setup/migrations and compare table row counts, tenant visibility under the application role, representative text ordering, pgvector dimensions and nearest-neighbour results, and index validity. Check database versions with the query below; for every application database also check `pg_collation.collversion` against `pg_collation_actual_version(oid)` where the stored version is non-null. Both mismatch counts must be zero.
5. Run the database and knowledge-store contract suites, then the integration tier. Switch application connections only after these checks and the healthcheck pass. Keep the old deployment read-only until the transition is accepted.

```sql
SELECT datname, datcollversion,
       pg_database_collation_actual_version(oid) AS actual
FROM pg_database
WHERE datallowconn
  AND datcollversion IS DISTINCT FROM pg_database_collation_actual_version(oid);
```

Validate every production extension, locale and workload in the isolated restored database before switching application connections.

## Rollback

Before writes resume, point the application back to the old deployment and its unchanged `pgdata` volume and image. After writes resume on trixie, reverting to that old snapshot would lose subsequent writes; restore or reconcile them through a separately reviewed recovery procedure. Never delete either volume as part of this transition. `docker compose down -v` is not an upgrade step.

## Restore an existing `pgdata` volume

The Compose project name is the same value used by `COMPOSE_PROJECT_NAME`, or the current directory name when that variable is unset. These commands preserve the old volume and write a logical dump before restoring it into the new Postgres service.

```bash
PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
docker run --rm -d --name gap-old-postgres -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" -v "${PROJECT}_pgdata:/var/lib/postgresql/data" pgvector/pgvector:pg16
until docker exec gap-old-postgres pg_isready -U postgres; do sleep 1; done
docker exec gap-old-postgres pg_dump -U postgres -Fc rag_platform > rag_platform-old.dump
docker stop gap-old-postgres
docker compose up -d --wait postgres
docker compose exec -T postgres createdb -U postgres rag_platform
docker compose exec -T postgres pg_restore -U postgres -d rag_platform --clean --if-exists < rag_platform-old.dump
scripts/setup_db.sh
```
