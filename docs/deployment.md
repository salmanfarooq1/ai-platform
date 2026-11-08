# Deployment

For local deployment and upgrade work. It covers the images, database roles and migrations, signing keys, workers, the optional Compose profiles and upgrade steps. Every setting is in [configuration.md](configuration.md).

`docker-compose.yml` is the sole active root Compose launcher and describes the local stack. Hosting is parked in [planning questions](../planning/QUESTIONS.md#parked-hosting); Sprint 015 will define the future deployment bundle. No production Compose launcher is supported by this guide.

## What runs

| Component | Image or command | Needs |
|---|---|---|
| API | `Dockerfile`, which runs `alembic upgrade head` and then uvicorn on port 8000 | Postgres 16 with pgvector, Valkey Search |
| Worker | the same image, `python -m workers` | the same stores, plus the object store the API uses |
| UI | `ui/Dockerfile.ui`, a static build served by nginx on port 80 | the API under the same site |
| Postgres | `pgvector/pgvector` for pg16 in compose | the `vector` extension |
| Valkey | `valkey/valkey-bundle` in compose | valkey-search; the Redis wire protocol keeps the existing cache port |

The API and workers are stateless. Run as many as needed: workers share the queue safely, and API processes share Postgres and Valkey.

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
| `docker compose up -d postgres valkey` | the stores |
| `docker compose up -d worker` | a worker |
| `docker compose --profile models up -d --wait ollama`, then `run --rm ollama-pull` | a local Ollama for local embeddings and models |
| `docker compose --profile observability up -d` | Prometheus and Grafana with the provisioned dashboard, on localhost |
| `docker compose --profile streams up -d --wait kafka`, then `run --rm kafka-topics` | Apache Kafka in single-node KRaft mode and its topics |
| `docker compose --profile lake up -d --wait seaweedfs`, then `run --rm seaweedfs-init` | the local S3 endpoint and the bucket named by `S3_BUCKET` |

Kafka, SeaweedFS and Ollama use upstream images pinned by tag and digest in `docker-compose.yml`. The image scan pulls and scans those exact artifacts; review any optional-profile critical findings through `scripts/supply_chain/image-exceptions.txt`. The supply-chain check builds the application and UI images and scans them alongside every digest-pinned Compose image. Existing Ollama stores follow [ollama-upgrade.md](ollama-upgrade.md); Compose keeps the original `ollama_data` and uses `ollama_data_v0407` for the reviewed runtime.

Every published port is bound to `127.0.0.1`. The default set is Postgres, Valkey and the worker; Kafka, object storage, local models and observability are optional. The worker waits for healthy stores, and each init job waits for its service. S3 credentials come from `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`; named local-only defaults support a fresh local setup. Override them for any shared installation.

Existing Grafana volumes follow [grafana-upgrade.md](grafana-upgrade.md). Compose uses `grafana_data_v13` for the upgraded image and preserves `grafana_data`; clone stopped complete state before upgrading an existing installation.

Existing Postgres volumes follow [postgres-upgrade.md](postgres-upgrade.md). Compose uses `pgdata_trixie`, preserves `pgdata`, and rejects mismatched collations in its healthcheck. Valkey uses `valkey_data` and leaves `redis_data` untouched.

Never use `docker compose down -v` to stop a profile. It also removes the Postgres volume.

## Hosting (parked)

No hosted deployment steps are currently supported. The earlier hosted setup remains in the historical planning records; resolve the open items under [Parked: hosting](../planning/QUESTIONS.md#parked-hosting) before Sprint 015 defines a deployment bundle.

## Upgrading
1. Back up the database.
2. Read the [changelog](../CHANGELOG.md) for new required settings.
3. Deploy the new image. Migrations run on start.
4. Restart the workers on the same image.
5. Check `/health`, and check `/metrics` or the Trust page for the eval gate and retention.
