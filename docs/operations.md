# Operations

For the person who runs the platform day to day. It covers health, metrics, keys, policies, retention, jobs, receipts, events on Kafka, sandboxed runs, the verify scripts and troubleshooting.

## Health
- **`GET /health`** (also at `/v1/health`) needs no key. It reports `db`, `redis` and `embedding` (each `ok` or an error), the `mode`, the `version` and `stale_vectors`. `status` is `ok` only when all three are `ok`.
- **What a failure means.** If Redis or the database is down, governed calls answer `503 dependency_unavailable`, and nothing runs without its decision record. If the embedding model is unreachable, searches and ingestion fail while the rest of the API works.
- **Workers** keep `WORKER_HEALTH_FILE` fresh while they run.
- **Logs** are JSON lines with `request_id`, `trace_id`, `tenant_id` and `principal_id`. Input text and secrets are never logged. Follow one request with its `request_id`, which every error body and response header also carries.

## Metrics
`/metrics` serves the Prometheus text format. It is open when `METRICS_PUBLIC` is true (the default in `local` mode), and otherwise needs a credential with `admin`. A worker can serve its own series on `WORKER_METRICS_PORT`.

| Series | Labels | Meaning |
|---|---|---|
| `http_requests_total` | route, method, status | Requests by route template. Unknown methods are labelled `OTHER` |
| `http_request_duration_seconds` | route, method, status | Latency histogram |
| `gateway_decisions_total` | action, outcome, stage | Gateway decisions |
| `jobs_total` | kind, status | Jobs by status |
| `outbox_lag_seconds` | none | Age of the oldest unsent outbox row |

Labels never hold tenant ids or user input. `docker compose --profile observability up -d` starts Prometheus and Grafana on localhost with the "Platform trust" dashboard. Set `GRAFANA_URL` so the Trust page links to it.

## Keys, principals and policies
All of this runs through `scripts/admin/identity.py`, with the owner URL in `MIGRATION_DATABASE_URL`.

| Command | Does |
|---|---|
| `create-tenant <slug>` | A tenant and its `default` knowledge base |
| `create-kb <tenant> <slug> [--description]` | A knowledge base |
| `create-principal <tenant> <user\|service\|agent> <name>` | A principal |
| `create-key <principal-id> --scopes ...` | A key. The secret is printed once |
| `revoke-key <prefix>` | Revokes a key from the next request on. Its web sessions and run tokens end too |
| `list-keys [--tenant <slug>]` | Key metadata, never secrets |
| `set-policy <tenant> <file.json>` | Publishes a new policy version, active from the next request |
| `show-policy <tenant>` | Prints the active policy |
| `set-retention <tenant> <days\|default>` | A tenant's decision retention, 30 days or more |

After a leaked key: revoke it, then check `/v1/decisions` filtered by the principal for what it did.

## Retention
- **What is kept.** Decision records are kept for `DECISION_RETENTION_DAYS` (90 by default), or for a tenant's own value. The floor is 30 days.
- **The purge.** A worker schedules a `purge_decisions` job per tenant every `RETENTION_SCHEDULE_INTERVAL_SECONDS`. The job writes a signed chain checkpoint, then deletes expired rows in batches of `PURGE_BATCH_SIZE`, and emits `platform.gateway.purge.v1`.
- **Checking it.** The Trust page and `GET /v1/trust/summary` show the oldest record and the last purge.
- **Other tables.** Jobs, outbox rows, processed events, sandbox events and raw files are kept until removed by an operator.

## Jobs
- **States.** A job is `queued`, then `running` under a lease, and ends `succeeded`, `failed` (no retry helps, for example an unreadable file) or `dead` (all attempts used).
- **Inspecting.** `GET /v1/jobs?status=dead` lists dead jobs, and each has an `error_code`. Error codes never contain exception text. The details are in the worker log, under the job id.
- **After a fix.** Submit the work again. A dead job stays as a record.
- **A stuck `running` job** is claimed again by another worker when its lease ends.
- **Ingestion** stores each upload once under its SHA-256, so uploading the same file again stores nothing new.

## Receipts and the chain
- **Verify one decision:** open the Trust page and paste a decision id, or verify offline:
  ```bash
  curl -H "Authorization: Bearer $GAP_KEY" localhost:8000/v1/receipts/<decision-id> > receipt.json
  curl -H "Authorization: Bearer $GAP_KEY" localhost:8000/v1/receipts/keys > keys.json
  poetry run python scripts/verify/receipt.py receipt receipt.json --keys keys.json
  ```
  The script imports nothing from the platform, so an auditor can run it on a separate machine.
- **Verify a tenant's whole chain:** `scripts/verify/receipt.py chain --dsn <owner-url> --tenant <tenant-uuid> --keys keys.json`.
- **What breaks verification.** A changed record, a cut link or a removed row breaks the chain. A purge does not, because its checkpoint is signed.
- **Receipts that are unavailable.** Records written before the chain existed answer `409 receipt_unavailable`, and a stored row that no longer matches its hash answers `409 chain_mismatch`. Treat a `chain_mismatch` as a possible tampering incident.
- **Key rotation** is described in [deployment.md](deployment.md#the-receipt-signing-key).

## Embeddings and stale vectors
Each chunk records the model that embedded it. After `EMBED_MODEL` changes, chunks of the old model are left out of search and counted in `stale_vectors`. To bring them back, ingest those documents again. `scripts/verify/stale_vectors.py` shows the behaviour on a throwaway database. A fallback model (`EMBED_FALLBACK_MODELS`) with another vector width is refused.

## Kafka
With `EVENT_BUS=kafka` the outbox relay publishes events to Kafka. Without it, events go to in-process subscribers and nothing here applies.

```
request -> decision + outbox row (one Postgres transaction)
        -> relay (worker) -> topic platform.<type>, key = tenant id
        -> consumer group KAFKA_GROUP_ID -> handler, deduped by CloudEvent id
        -> after KAFKA_MAX_ATTEMPTS failures: platform.<type>.dlq
```

**Run it locally**
```bash
docker compose --profile kafka up -d redpanda        # one node, localhost:19092
docker compose --profile kafka up kafka-topics       # creates the topics with 3 partitions, then exits
EVENT_BUS=kafka KAFKA_BOOTSTRAP=localhost:19092 poetry run python -m workers
docker exec redpanda rpk topic consume platform.gateway.decision -n 3
```

Stop it with `docker compose --profile kafka rm -sf kafka-topics redpanda`.

**How it behaves**
- **Kafka is never reached inside a request.** If Kafka is down, events wait in the outbox and the relay retries them. After `OUTBOX_MAX_ATTEMPTS` a row is left for an operator.
- **Order.** A tenant's events stay in order. The relay stops a tenant's batch at its first failed row, so a later row never overtakes it. Repartitioning a topic with data can move a tenant to another partition, so its old and new events may then interleave.
- **Duplicates.** Delivery is at least once. Consumers must dedupe by CloudEvent id: use `IdempotentConsumer` or `KafkaEventBus.consume`, which record ids in `processed_events`.
- **Failed handling.** A failed handler, dead-letter send or commit rewinds the consumer to that record, so nothing is skipped.
- **Dead letters.** A record in `<topic>.dlq` has these headers: `x-error` (the exception class), `x-error-code` (`handler_failed` or `decode_failed`), `x-original-topic`, `x-original-partition`, `x-original-offset` and `x-attempts`. The error message is left out because it may hold input. Look in the consumer log by event id. Fix the cause, then publish the record to its topic again. Consumers that already handled it skip it.
- **Lag.** `rpk group describe <group>` shows consumer lag, and `outbox_lag_seconds` shows the outbox side.
- **Switching back.** Set `EVENT_BUS=outbox` and restart the relay. No migration is needed.
- **Supported setup.** One broker. `aiokafka` is pinned in `pyproject.toml`. The producer uses `acks=all` and is idempotent. SASL settings come from the environment and are never logged.

## Sandboxed runs (OpenShell)
With `AGENT_RUNTIME=openshell`, each agent run executes inside an [OpenShell](https://github.com/NVIDIA/OpenShell) sandbox (Apache-2.0), version 0.1.2 with the Docker driver.

**Host requirements**
- Linux with Docker 28 or newer. Landlock ABI 3 or newer (Linux 6.2 or newer, with Landlock enabled). Seccomp user notification. glibc 2.28 or newer.
- To check Landlock on x86_64, run `python3 -c "import ctypes; print(ctypes.CDLL(None).syscall(444, None, 0, 1))"`. It prints the ABI number. A negative number means no Landlock.

**Install, pinned by checksum.** Never run an unpinned install script.
```bash
B=https://github.com/NVIDIA/OpenShell/releases/download/v0.1.2
curl -fsSL -o openshell.deb $B/openshell_0.1.2-1_amd64.deb
echo "1f5416ea08f32fdc621f20a2cc0324298e60aba8bbe996459d9e3b44195f23df  openshell.deb" | sha256sum -c -
sudo dpkg -i openshell.deb
systemctl --user enable --now openshell-gateway
openshell gateway add https://127.0.0.1:17670 --local --name openshell
poetry run pip install --no-deps --require-hashes -r scripts/verify/openshell-requirements.txt   # the Python SDK
```

The gateway must use mTLS. The SDK is not a runtime dependency of the default image, and the platform imports it only when the runtime is selected.

**The workload image**, set as `OPENSHELL_IMAGE`, needs:
- `python3`
- a non-root user `sandbox`, with `USER sandbox`
- the work directory (`/sandbox/work` by default), owned by that user

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y python3 && rm -rf /var/lib/apt/lists/*
RUN useradd -m sandbox && mkdir -p /sandbox/work && chown sandbox:sandbox /sandbox/work
USER sandbox
CMD ["sleep", "infinity"]
```

Pin every image by digest on first pull (`docker image inspect --format '{{index .RepoDigests 0}}' <image>`).

**Platform settings**
```bash
AGENT_RUNTIME=openshell
SANDBOX_GATEWAY_URL=http://172.17.0.1:8000     # this API as the sandbox sees it; loopback is refused by OpenShell
OPENSHELL_IMAGE=<workload image>
```

Run the worker on the host that has Docker and the gateway. The API keeps queueing runs as jobs. Limits are `SANDBOX_CPU`, `SANDBOX_MEMORY` and `SANDBOX_WALL_SECONDS`.

**Notes**
- The run token crosses the local Docker bridge over HTTP. It lives for the wall limit plus a minute, and works only on its run's two routes.
- A network rule names the interpreter by its real path, not a symlink. The default for `SANDBOX_NETWORK_BINARIES` is `/usr/bin/python3*`.
- OpenShell logs no event for a refused file read. The process gets a permission error.
- A run over the memory limit exits 137 and is recorded as `limit_hit`.

**Troubleshooting**

| You see | Fix |
|---|---|
| `docker sandboxes require launch-scoped gateway authentication` | Run the gateway with mTLS and register it with `--local` |
| `workload identity must not contain UID or GID zero` | Add the `sandbox` user and `USER sandbox` to the image |
| `No such image: sha256:...` from the gateway | An image was rebuilt after the gateway started. Restart the gateway |
| Every gateway call denied with `transparent_tcp_policy_denied` | Add the interpreter's real path (`readlink -f $(which python3)` in the image) to `SANDBOX_NETWORK_BINARIES` |
| `the sandbox image has no work directory` | Build the work directory into the image, owned by `sandbox` |
| The run fails with `sandbox_unavailable` | The sandbox did not start. The worker log has the gateway's reason, and `openshell status` shows whether the gateway is up |
| The run fails with `wall_time_exceeded` | It reached `SANDBOX_WALL_SECONDS` |
| The run fails with `bad_output` | The agent's last line was not `{"result": ...}`, or the output was over 1 MiB |

## Verify scripts
These check the platform against real services that the test suite replaces with fakes.

| Script | Checks |
|---|---|
| `scripts/verify/minio.sh` | The object store contract against a live MinIO |
| `scripts/verify/kafka.sh` | The Kafka adapter, ordering, dead letters and relay restart against a live broker. It starts the `kafka` profile, or uses `KAFKA_BOOTSTRAP` |
| `scripts/verify/openshell.sh` | Sandboxed runs end to end: allowed task, blocked provider call, refused read, limits, argument deny |
| `scripts/verify/observability.sh` | Prometheus scrapes the API, and Grafana serves the dashboard |
| `scripts/verify/receipt.py` | A receipt verifies offline |
| `scripts/verify/stale_vectors.py` | Stale vectors are ignored and counted |
| `scripts/verify/migration_0007.py` | The provenance backfill on a copy of old data |
| `scripts/verify/lighthouse.sh` | Landing page performance |
| `scripts/eval/run_gate.py` | The eval gate with test models, as in CI |
| `scripts/eval/run_real.py` | The eval suite with real providers. Needs keys and `REAL_EVAL=1` |

## Troubleshooting

| You see | Cause and fix |
|---|---|
| The API stops at start with a settings error | A required value is missing or wrong. The message names the variable ([configuration.md](configuration.md)) |
| The API refuses to start as the database owner | `DATABASE_URL` must be the `gap_app` role |
| The API does not start, with an unknown `FT.CREATE` command | Redis has no RediSearch module |
| `503 dependency_unavailable` | Redis or the database is unreachable. Check `/health` |
| `503 decision_unrecorded` | The decision record could not be written, so the call did not run. Check the database and the logs for the request id |
| `429 cost_cap_exceeded` or `daily_token_budget_exceeded` | The tenant reached its daily limit. It resets at midnight UTC, or raise the platform value |
| An ingest stays `queued` | No worker is running |
| An agent query answers `202` | The run takes longer than `AGENT_SYNC_WAIT_SECONDS`. Poll `/v1/agent/runs/{execution_id}` |
| Search returns nothing after a model change | The old chunks are stale. Check `stale_vectors` and ingest again |
| The UI signs in, but governance screens are empty | The key lacks `audit:read` |
