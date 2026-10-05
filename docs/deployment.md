# Deployment

For the person who deploys or upgrades the platform. It covers the images, the database roles and migrations, the signing key, workers, the optional compose profiles, the hosted setup and the upgrade steps. Every setting is in [configuration.md](configuration.md).

## What runs

| Component | Image or command | Needs |
|---|---|---|
| API | `Dockerfile`, which runs `alembic upgrade head` and then uvicorn on port 8000 | Postgres 16 with pgvector, Redis with RediSearch |
| Worker | the same image, `python -m workers` | the same stores, plus the object store the API uses |
| UI | `ui/Dockerfile.ui`, a static build served by nginx on port 80 | the API under the same site |
| Postgres | `pgvector/pgvector` for pg16 in compose | the `vector` extension |
| Redis | `redis/redis-stack-server` in compose | the RediSearch module. Without it the API does not start |

The API and workers are stateless. Run as many as needed: workers share the queue safely, and API processes share Postgres and Redis.

## Images

```bash
docker build -t gap-platform .                              # API and worker
docker build --build-arg INCLUDE_RERANK=true -t gap-platform-rerank .
docker build -f ui/Dockerfile.ui -t gap-ui ui
```

- `INCLUDE_RERANK=false` (the default) leaves out the cross-encoder and torch. The image is about 120 MiB. With `true`, the reranker is available and the image is several GB.
- The image's health check calls `/health`.

## Database roles

The platform uses two roles:
- **Owner role:** runs the migrations and the admin CLI. Set it in `MIGRATION_DATABASE_URL`.
- **App role `gap_app`:** `LOGIN NOSUPERUSER NOBYPASSRLS`. The API and workers connect with it, through `DATABASE_URL`. The API refuses to start as a superuser or a role that bypasses row-level security.

Create the app role once, as the owner, before the first migration:

```sql
CREATE ROLE gap_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '<generated>';
GRANT CONNECT ON DATABASE <database> TO gap_app;
```

Each migration grants the app role exactly the rights it needs, so there are no default privileges. If the app role has another name, run `psql "$MIGRATION_DATABASE_URL" -v app_role=<name> -f scripts/admin/grant_app_role.sql` after the migrations. Locally, `docker/postgres-init` creates `gap_app` on a fresh volume and `bash scripts/setup_db.sh` does the rest.

## Migrations

Migrations are forward only, and the API image applies them on start. Check the head with `poetry run alembic current`, which needs the owner URL.

| Migration | Adds |
|---|---|
| `0001` | The baseline schema: documents, registry, usage, feedback. On a database that already has these tables it only records the version |
| `0002` | Tenants, principals, keys, knowledge bases, `tenant_id` on tenant data, row-level security. Existing rows go to the tenant `default` |
| `0003` | The principal lookup used by JWT authentication |
| `0004` | Least privilege for the app role |
| `0005` | Policies and decision records |
| `0006` | The preview principal lookup |
| `0007` | `embedding_model` and `embedding_dim` on documents, and `execution_id` on decisions |
| `0008` | Jobs, the outbox and processed events |
| `0009` | The hash chain, chain checkpoints, retention and eval runs |
| `0010` | Sandbox events and run tokens |

Two migrations need care on a database that already holds data:
- **`0002`** recreates indexes on live tables and holds a short lock. Run it at a quiet time.
- **`0007`** labels existing documents with the configured `EMBED_MODEL` and `EMBEDDING_DIM`, then makes the columns required. Set those two values to the model that produced the stored vectors. Deploy `0007` together with the new image, because an older image cannot insert a document once the columns are required.

## The receipt-signing key

`RECEIPT_SIGNING_KEY` is an Ed25519 private key, given as base64 of 32 bytes. It is required outside `local` mode.

- **Same key everywhere.** The API and every worker must use the same key.
- **Storage.** Keep it in the host's secret store. It is never written to disk by the platform.
- **Rotation.** Set the new key, and add the old public key to `RECEIPT_PREVIOUS_PUBLIC_KEYS`, so receipts signed before the rotation still verify.
- **Local mode.** A throwaway key is generated at start. Receipts signed with it cannot be verified after a restart.

## Workers

Ingestion, agent runs, the retention purge and the outbox relay need a worker. Run one of these:

```bash
poetry run python -m workers --concurrency 2                    # a worker process (also relays the outbox)
docker compose up -d worker                                     # the same, in compose
EMBEDDED_WORKERS=1 EMBEDDED_RELAY=true uvicorn api.main:app     # inside the API process, for a single-container host
```

- **Health.** A worker keeps `WORKER_HEALTH_FILE` fresh while it runs, and the compose health check reads it.
- **Shutdown.** On SIGTERM it stops claiming, gives a running job a grace period, and then releases that job's lease so another worker can take it.
- **Sandboxed runs.** For `AGENT_RUNTIME=openshell` the worker must run on a host with Docker and an OpenShell gateway. See [operations.md](operations.md#sandboxed-runs-openshell).

## Compose profiles

| Command | Starts |
|---|---|
| `docker compose up -d postgres redis` | the stores |
| `docker compose up -d worker` | a worker |
| `docker compose up -d ollama` | a local Ollama for local embeddings and models |
| `docker compose --profile observability up -d` | Prometheus and Grafana with the provisioned dashboard, on localhost |
| `docker compose --profile kafka up -d redpanda` and `up kafka-topics` | a single-node Kafka-compatible broker and its topics |

Never use `docker compose down -v` to stop a profile. It also removes the Postgres volume.

## Hosted setup

`render.yaml` describes a hosted setup on Render: the API service (Docker, `/health` check) and the UI service. Values marked `sync: false` are entered as secrets in the dashboard. To deploy:
1. Back up the database.
2. Create the `gap_app` role. Set `MIGRATION_DATABASE_URL` to the owner and `DATABASE_URL` to `gap_app`.
3. Set `MODE=public-preview`, `REDIS_URL`, `RECEIPT_SIGNING_KEY` and the model keys.
4. Deploy the API. Its start command applies the migrations.
5. Run a worker (`EMBEDDED_WORKERS=1` on a single-service plan).
6. For a read-only preview: create a principal and a key with `query kb:read agent`, and set `PREVIEW_PRINCIPAL_ID` to that principal.
7. Check: `/health` shows `db`, `redis` and `embedding` as `ok`. `/v1/documents` without a key gives `401`, and with a key gives the documents.

Notes for hosted stores:
- **Neon's pooled endpoint.** It works because the pool disables asyncpg's prepared-statement cache.
- **Redis.** It must include RediSearch (Redis Cloud does; Upstash does not).
- **Free instances.** Some free tiers stop idle instances, so the first request after a pause is slow.

## Upgrading
1. Back up the database.
2. Read the [changelog](../CHANGELOG.md) for new required settings.
3. Deploy the new image. Migrations run on start.
4. Restart the workers on the same image.
5. Check `/health`, and check `/metrics` or the Trust page for the eval gate and retention.
