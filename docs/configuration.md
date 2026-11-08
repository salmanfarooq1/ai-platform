# Configuration

For anyone who runs the platform. It lists every setting, what it does, its default, and whether it is a secret.

## How settings are read
- **Source.** Settings come from environment variables, or from a `.env` file in local development. The names are the setting names in upper case. `.env.example` is a starting point. Never put a real secret in a file in the repository.
- **One object.** `core/settings.py` defines one validated `Settings` object. Every module reads it and nothing reads `os.environ` directly.
- **Fail fast.** A wrong type, an unknown `MODE`, or a value that a mode requires but is missing stops the process at startup. The error names the variable and never prints its value.
- **Secrets.** Secret values are held as secret types, so they do not appear in logs, errors or reprs.

## Modes
`MODE` picks the defaults and the required values.

| Mode | For | Required beyond the defaults |
|---|---|---|
| `local` | development on one machine | none. Database and Redis default to the compose services, and an ephemeral receipt-signing key is generated |
| `public-preview` | a hosted instance open to visitors, with an optional read-only preview session | `DATABASE_URL`, `REDIS_URL` and `RECEIPT_SIGNING_KEY`. Every configured model must have a price, or the process refuses to start |
| `prod` | a production instance | the same as `public-preview`. `PREVIEW_PRINCIPAL_ID` is refused |

Some values become required by another choice:
- `EVENT_BUS=kafka` needs `KAFKA_BOOTSTRAP`. A SASL protocol needs the mechanism, user name and password.
- `OBJECT_STORE=s3` needs the bucket and its credentials.
- `AGENT_RUNTIME=openshell` needs `SANDBOX_GATEWAY_URL`.
- JWT verification needs exactly one of `JWT_SECRET` (at least 32 characters) and `JWT_JWKS_URL`, plus `JWT_ISSUER` and `JWT_AUDIENCE`.

Model provider keys (for example `GEMINI_API_KEY`) are read by LiteLLM from the environment. `MIGRATION_DATABASE_URL` falls back to `DATABASE_URL`, but in a hosted setup it should be the owner role while `DATABASE_URL` is `gap_app`.

When the API and a separate worker run, they must share the same `RECEIPT_SIGNING_KEY`, or purge checkpoints are signed with a key the API does not list. To make a key:

```bash
python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"
```

## Tenant policy
Per-tenant limits live in the tenant's policy, not in settings. A policy can only narrow the platform values below. For example, `daily_cost_cap_usd` can be lower than `DAILY_COST_CAP_USD`, never higher. The policy fields are described in [api/README.md](api/README.md#policies).

## Settings

This table is generated from `core/settings.py` by `scripts/docs/generate.py`. Do not edit it by hand.

<!-- BEGIN GENERATED: settings -->
### Mode and data stores

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `MODE` | `local` | no | Deployment mode: `local`, `public-preview` or `prod`. It picks the model defaults and which values are required. |
| `DATABASE_URL` | unset | yes | Postgres URL the app connects with. It must be a role that is neither superuser nor BYPASSRLS. Required outside local mode; local mode defaults to the `gap_app` role of the compose Postgres. |
| `MIGRATION_DATABASE_URL` | unset | yes | Postgres URL of the owner role, used by Alembic and `scripts/admin/identity.py`. Falls back to `DATABASE_URL`; local mode defaults to the compose superuser. |
| `REDIS_URL` | unset | yes | Valkey or Redis URL. The server needs a search module (valkey-search). Required outside local mode; local mode defaults to `redis://localhost:6379`. |

### Models and embeddings

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `LLM_MODEL` | unset | no | LiteLLM model name for completions. Default by mode: `gemini/gemini-3.5-flash-lite` (local, public-preview), `azure/gpt-4o` (prod). |
| `EMBED_MODEL` | unset | no | LiteLLM model name for embeddings. Default by mode: `ollama/nomic-embed-text` (local), `gemini/gemini-embedding-001` (public-preview), `azure/text-embedding-3-small` (prod). Chunks record the model that made them, and search ignores chunks of another model. |
| `EMBEDDING_DIM` | `768` | no | Width of every stored vector. It must match the `vector` column of the schema. |
| `EMBED_FALLBACK_MODELS` | unset | no | Comma separated embedding models tried in order when the primary fails. A model whose vectors have another width than `EMBEDDING_DIM` is refused. Empty means no fallback. |
| `AZURE_OAI_BASE` | unset | no | Azure OpenAI endpoint. Used by `azure/...` models. |
| `AZURE_OAI_KEY` | unset | yes | Azure OpenAI key. Used by `azure/...` models. |
| `GROQ_API_KEY` | unset | yes | Groq API key. Used only when `LLM_MODEL` names a Groq model. |

### Object store

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `OBJECT_STORE` | `local` | no | Object store adapter for raw uploads: `local` writes files under `OBJECT_STORE_DIR`, `s3` uses an S3 API (R2, MinIO, S3). |
| `OBJECT_STORE_DIR` | `data/objects` | no | Directory of the `local` object store. |
| `S3_ENDPOINT_URL` | unset | no | S3 API endpoint. Required when `OBJECT_STORE=s3`. |
| `S3_BUCKET` | unset | no | S3 bucket name. Required when `OBJECT_STORE=s3`. |
| `S3_REGION` | `auto` | no | S3 region. |
| `S3_ACCESS_KEY_ID` | unset | yes | S3 access key id. Required when `OBJECT_STORE=s3`. |
| `S3_SECRET_ACCESS_KEY` | unset | yes | S3 secret access key. Required when `OBJECT_STORE=s3`. |

### Events

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `EVENT_BUS` | `outbox` | no | Event bus: `outbox` writes events in the transaction of the change and a relay publishes them, `kafka` makes the relay publish to Kafka, `inprocess` keeps events in the API process (tests and tools). |
| `KAFKA_BOOTSTRAP` | unset | no | Comma separated `host:port` list of Kafka brokers. Required when `EVENT_BUS=kafka`. |
| `KAFKA_CLIENT_ID` | `gap-platform` | no | Kafka client id. |
| `KAFKA_GROUP_ID` | `gap-platform` | no | Kafka consumer group. |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | no | Kafka security protocol. A SASL protocol needs the three `KAFKA_SASL_*` values. |
| `KAFKA_SASL_MECHANISM` | unset | no | SASL mechanism. Required with a SASL protocol. |
| `KAFKA_SASL_USERNAME` | unset | no | SASL user name. Required with a SASL protocol. |
| `KAFKA_SASL_PASSWORD` | unset | yes | SASL password. Required with a SASL protocol. Set it in the environment only. |
| `KAFKA_MAX_ATTEMPTS` | `5` | no | Tries a consumer makes for a message before it goes to `<topic>.dlq`. |
| `KAFKA_RETRY_BACKOFF_SECONDS` | `0.5` | no | Pause between consumer tries, in seconds. |
| `KAFKA_REQUEST_TIMEOUT_SECONDS` | `10.0` | no | Limit of one request to the broker, in seconds. |
| `KAFKA_SEND_TIMEOUT_SECONDS` | `15.0` | no | Limit of one send with its acknowledgement, in seconds. The relay holds a row lock meanwhile, so keep it short. |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | no | How often the outbox relay looks for unpublished events, in seconds. |
| `OUTBOX_BATCH_SIZE` | `50` | no | Events the outbox relay takes in one pass. |
| `OUTBOX_MAX_ATTEMPTS` | `10` | no | Tries the relay makes for one event before it leaves the row for an operator. |

### Agent runtime and sandbox

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `AGENT_RUNTIME` | `queued` | no | Agent runtime: `queued` runs each agent run as a job in a worker, `openshell` runs it in an OpenShell sandbox started by a worker, `inprocess` runs it in the API process. |
| `AGENT_SYNC_WAIT_SECONDS` | `25.0` | no | How long `POST /v1/agent/query` waits for the worker before it answers 202 with the execution id. |
| `SANDBOX_GATEWAY_URL` | unset | no | Address of this API as the sandbox sees it. It is the only host the sandbox may connect to, and it must not be loopback. Required when `AGENT_RUNTIME=openshell`. |
| `OPENSHELL_ENDPOINT` | unset | no | OpenShell gateway `host:port`. Unset uses the active gateway of the OpenShell CLI configuration. |
| `OPENSHELL_WORKSPACE` | `default` | no | OpenShell workspace name. |
| `OPENSHELL_IMAGE` | unset | no | Workload image of the sandbox. It needs `python3`, a user named `sandbox` and the work directory. Unset uses the OpenShell default image, which has no `python3`. |
| `SANDBOX_CPU` | `1` | no | CPU limit of a sandbox, for example `1` or `500m`. |
| `SANDBOX_MEMORY` | `512Mi` | no | Memory limit of a sandbox, for example `512Mi`. |
| `SANDBOX_WALL_SECONDS` | `300` | no | Wall-clock limit of a sandboxed run, in seconds. It is also the life of the run token, plus a minute. |
| `SANDBOX_WORK_DIR` | `/sandbox/work` | no | The one directory a sandbox may write. It must exist in the image. An absolute path other than `/`. |
| `SANDBOX_READ_ONLY_PATHS` | `/usr,/lib,/lib64,/bin,/sbin` | no | Comma separated system paths a sandbox may read so `python3` can start. Nothing else outside the work directory is readable. |
| `SANDBOX_NETWORK_BINARIES` | `/usr/bin/python3*` | no | Comma separated real paths or globs of the executables that may open the sandbox's one network route. A symlink does not match. |

### Jobs and workers

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `JOB_LEASE_SECONDS` | `60` | no | Lease of a claimed job, in seconds. A worker renews it while the job runs; a lost lease lets another worker take the job. |
| `JOB_POLL_INTERVAL_SECONDS` | `0.5` | no | How often an idle worker looks for a job, in seconds. |
| `JOB_BEAT_INTERVAL_SECONDS` | `1.0` | no | How often a running job renews its lease and looks for a stop request, in seconds. |
| `JOB_MAX_ATTEMPTS` | `5` | no | Tries a job gets before it ends `dead`. |
| `JOB_BACKOFF_BASE_SECONDS` | `2.0` | no | Base of the retry delay in seconds. The delay is the base times 2 to the power of the attempts, with jitter. |
| `WORKER_CONCURRENCY` | `1` | no | Jobs one worker process runs at the same time. |
| `WORKER_HEALTH_FILE` | `/tmp/worker-health` | no | File a worker touches while it is healthy. The compose health check reads its age. |
| `WORKER_SHUTDOWN_GRACE_SECONDS` | `30.0` | no | How long a worker waits for running jobs after SIGTERM, in seconds. |
| `EMBEDDED_WORKERS` | `0` | no | Number of workers to run inside the API process. 0 means none. For hosts that run one container. |
| `EMBEDDED_RELAY` | `false` | no | Run the outbox relay inside the API process. |
| `WORKER_METRICS_PORT` | `0` | no | Port where a worker serves its own metrics. 0 turns it off. |

### Limits and guardrails

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `MAX_QUERY_LENGTH` | `1,000` | no | Longest question the input guardrail accepts, in characters. |
| `CONFIDENCE_FLOOR` | `0.45` | no | Retrieval score below which the output guardrail flags an answer. |
| `RATE_LIMIT_REQUESTS` | `60` | no | Requests one principal may make in a rate-limit window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | no | Length of the rate-limit window, in seconds. |
| `DAILY_TOKEN_BUDGET` | `500,000` | no | Tokens a tenant may use per UTC day. |
| `DAILY_COST_CAP_USD` | `10.0` | no | Cost a tenant may spend per UTC day, in USD. A tenant policy may set a lower cap, never a higher one. |

### Receipts and retention

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `RECEIPT_SIGNING_KEY` | unset | yes | Ed25519 private key for receipts: base64 of 32 raw bytes. Required in `public-preview` and `prod`; local mode makes a throwaway key at startup. Set the same key in the API and every worker. |
| `RECEIPT_PREVIOUS_PUBLIC_KEYS` | unset | no | Comma separated base64 public keys of earlier signing keys. They stay listed after a rotation so older receipts still verify. |
| `DECISION_RETENTION_DAYS` | `90` | no | Days decision records are kept. A tenant may set its own value. The minimum is 30. |
| `PURGE_BATCH_SIZE` | `1,000` | no | Decision rows one purge step deletes. |
| `RETENTION_SCHEDULE_INTERVAL_SECONDS` | `3600.0` | no | How often a worker looks for tenants with expired records and queues a purge job (one a day per tenant). 0 turns the scheduler off. |

### Identity and web edge

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `JWT_JWKS_URL` | unset | no | JWKS URL for JWT verification with asymmetric keys. Set only one of this and `JWT_SECRET`. |
| `JWT_SECRET` | unset | yes | HS256 secret for JWT verification, at least 32 characters. Set only one of this and `JWT_JWKS_URL`. |
| `JWT_ISSUER` | unset | no | Expected JWT issuer. Required when JWT verification is on. |
| `JWT_AUDIENCE` | unset | no | Expected JWT audience. Required when JWT verification is on. |
| `FRONTEND_URL` | unset | no | Extra origin allowed by CORS. The Vite dev and preview ports on localhost are always allowed. |
| `PREVIEW_PRINCIPAL_ID` | unset | no | Principal id (a UUID, never a key) that a visitor gets a read-only session for at `POST /v1/session/preview`. Used only when `MODE=public-preview`, and not allowed when `MODE=prod`. |

### Observability and process

| Setting | Default | Secret | Purpose |
|---|---|---|---|
| `METRICS_PUBLIC` | unset | no | `/metrics` is open when true and needs the `admin` scope when false. Unset means true in local mode and false elsewhere. |
| `GRAFANA_URL` | unset | no | Link the Trust page shows when the observability profile runs, for example `http://localhost:3000`. |
| `WEB_CONCURRENCY` | `1` | no | Number of API worker processes you run. The API logs the total database connection budget from it. |
| `LOG_LEVEL` | `INFO` | no | Log level of the JSON logs. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset | no | OTLP endpoint for traces. Unset means no exporter and no background thread. |
| `OTEL_SERVICE_NAME` | `ai-platform-api` | no | Service name on exported traces. |
<!-- END GENERATED: settings -->
