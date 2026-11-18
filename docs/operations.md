# Operations

For the person who runs the platform day to day. It covers health, metrics, keys, policies, retention, jobs, receipts, events on Kafka, sandboxed runs, the verify scripts and troubleshooting.

## Health
- **`GET /health`** (also at `/v1/health`) needs no key. It reports `db`, `redis` and `embedding` (each `ok` or an error), the `mode`, the `version` and `stale_vectors`. `status` is `ok` only when all three are `ok`.
- **What a failure means.** If Valkey or the database is down, governed calls answer `503 dependency_unavailable`, and nothing runs without its decision record. If the embedding model is unreachable, searches and ingestion fail while the rest of the API works.
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

Operator Python callers can use `gateway.admin.set_policy(..., expected_version=head_version)` inside `admin_connection`. A changed head raises public `PolicyConflict`, a subclass of `AdminError`, without publishing a policy. Use version 0 to require no existing policy; omit the argument for unconditional publication. The caller commits or rolls back the transaction.

The public owner-role functions in `core.identity.admin` also support operator Python clients:
`inspect_credential(conn, token)` verifies an active key and returns only tenant ID and slug,
principal ID and kind, prefix and scopes. It never returns a secret or hash.
`list_principals(conn, tenant_slug)` and `list_kbs(conn, tenant_slug)` list a tenant's
principal metadata and knowledge bases. `list_keys(conn, tenant_slug, principal_id=...)`
sets transaction-local tenant context and filters metadata by tenant and optionally principal.
Omitting the tenant explicitly requests an operator-wide listing, subject to the connection role's visibility.
These functions do not grant runtime permissions.

`GET /v1/decisions?request_id=...` is available in the Gateway edition with `audit:read`.
It returns only the verified caller's tenant decisions, including recorded module denials.

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
docker compose --profile streams up -d kafka        # one node, localhost:19092
docker compose --profile streams run --rm kafka-topics       # creates the topics with 3 partitions, then exits
EVENT_BUS=kafka KAFKA_BOOTSTRAP=localhost:19092 poetry run python -m workers
docker compose --profile streams exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic platform.gateway.decision --max-messages 3
```

Stop it with `docker compose --profile streams stop kafka`.

Topic initialization creates the three platform topics and their `.dlq` topics with three partitions, replication factor one and `retention.ms=604800000` (seven days). This is broker retention, separate from durable decision retention in Postgres. Re-running initialization is idempotent. The local profile uses plaintext listeners; SASL/TLS and ACLs need a separately secured deployment. Host clients use `KAFKA_BOOTSTRAP=localhost:19092`; containers use `kafka:9092`.

**How it behaves**
- **Kafka is never reached inside a request.** If Kafka is down, events wait in the outbox and the relay retries them. After `OUTBOX_MAX_ATTEMPTS` a row is left for an operator.
- **Order.** A tenant's events stay in order. The relay stops a tenant's batch at its first failed row, so a later row never overtakes it. Repartitioning a topic with data can move a tenant to another partition, so its old and new events may then interleave.
- **Duplicates.** Delivery is at least once. Consumers must dedupe by CloudEvent id: use `IdempotentConsumer` or `KafkaEventBus.consume`, which record ids in `processed_events`.
- **Failed handling.** A failed handler, dead-letter send or commit rewinds the consumer to that record, so nothing is skipped.
- **Dead letters.** A record in `<topic>.dlq` has these headers: `x-error` (the exception class), `x-error-code` (`handler_failed` or `decode_failed`), `x-original-topic`, `x-original-partition`, `x-original-offset` and `x-attempts`. The error message is left out because it may hold input. Look in the consumer log by event id. Fix the cause, then publish the record to its topic again. Consumers that already handled it skip it.
- **Lag.** `docker compose --profile streams exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group <group>` shows consumer lag, and `outbox_lag_seconds` shows the outbox side.
- **Switching back.** Set `EVENT_BUS=outbox` and restart the relay. No migration is needed.
- **Supported setup.** One broker. `aiokafka` is pinned in `pyproject.toml`. The producer uses `acks=all` and is idempotent. SASL settings come from the environment and are never logged.

Grafana upgrades use a new volume and the [stopped-state clone procedure](grafana-upgrade.md), preserving the previous volume for rollback.

## Valkey and local S3

Valkey Search stores only derived responses, session state and shared governance counters. Response-cache lookup/write failures degrade to a miss or an uncached response. Rate, token-budget and daily-cost stages keep failing closed with `503 dependency_unavailable` if the shared store is unavailable; no process-local counters replace them. The public health field and setting remain `redis` and `REDIS_URL` for compatibility.

The lake profile uses the upstream SeaweedFS image pinned by tag and digest in `docker-compose.yml`. Start the endpoint before running its bucket-init job.
```bash
docker compose --profile lake up -d --wait seaweedfs
```
This starts the loopback S3 endpoint on port 8333. Set `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` and `S3_BUCKET`, then run `docker compose --profile lake run --rm seaweedfs-init`. The mounted IAM configuration expands environment placeholders, so credentials are not stored in it. The init job limits per-bucket volume growth to one and creates the configured bucket. Data and filer metadata live in `seaweedfs_data`. The local principal is shared; per-tenant S3 identities are outside this setup.

For live verification, set `S3_LIVE_ENDPOINT`, `S3_LIVE_ACCESS_KEY`, `S3_LIVE_SECRET_KEY` and `S3_LIVE_BUCKET`, then run `scripts/verify/seaweedfs.sh`. It checks content-addressed reads/writes, invalid keys, missing objects, repeat writes and boto3 SigV4 signed GET/PUT. Signed URLs and credentials are never printed.

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
| `scripts/verify/seaweedfs.sh` | The live SeaweedFS S3 contract and boto3 signed GET/PUT |
| `scripts/verify/kafka.sh` | The Kafka adapter, ordering, dead letters and relay restart against a live broker. It starts the `streams` profile, or uses `KAFKA_BOOTSTRAP` |
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
| The API does not start, with an unknown `FT.CREATE` command | The cache service has no compatible search module |
| `503 dependency_unavailable` | Valkey or the database is unreachable. Check `/health` |
| `503 decision_unrecorded` | The decision record could not be written, so the call did not run. Check the database and the logs for the request id |
| `429 cost_cap_exceeded` or `daily_token_budget_exceeded` | The tenant reached its daily limit. It resets at midnight UTC, or raise the platform value |
| An ingest stays `queued` | No worker is running |
| An agent query answers `202` | The run takes longer than `AGENT_SYNC_WAIT_SECONDS`. Poll `/v1/agent/runs/{execution_id}` |
| Search returns nothing after a model change | The old chunks are stale. Check `stale_vectors` and ingest again |
| The UI signs in, but governance screens are empty | The key lacks `audit:read` |

## Persistent local receipt keys

Keep `.poc/<stack>/receipt-signing.key` and `restic-password` outside runtime
volumes. The operator key helper creates these files once with mode 0600 inside
0700 directories; unsafe files refuse reuse. A restore requires the original
files. Removing runtime volumes must preserve the entire `.poc/<stack>/` directory.

Set `RECEIPT_SIGNING_KEY_FILE` to the mounted file path in both API and worker.
The key helper's Compose override binds that same host file read-only at
`/run/secrets/receipt-signing.key` in both services and refuses a missing source.
Only the path goes into Compose or the environment. Do not also configure
`RECEIPT_SIGNING_KEY`. Stop and restart both processes after changing the file.

Copy the private key and repository password separately to protected offline
storage. Preserve mode 0600 and private parent directories. Never include either
in the data snapshot, build context, logs or evidence. Protect the two offline
copies independently; losing the repository password prevents reading the backup.
Before recovery, derive the public identity from the recovered private file and
compare its key id **and public bytes** with the saved public metadata.

The data manifest may contain only `key_id` and base64 `public_key`. A different
active key is accepted only if `RECEIPT_PREVIOUS_PUBLIC_KEYS` explicitly contains
the exact previous public bytes and their derived id matches the manifest.
A previous public key cannot replace a missing active private file. Keep trusted
public keys with saved receipts so offline verification survives rotation.

## Local POC stack: `poc up`
`poetry run python scripts/poc up <stack>` starts one isolated stack: Postgres, Valkey, API and worker, and nothing
else (optional profiles stay off, whatever `COMPOSE_PROFILES` says). The stack name is 3 to 31 characters (`a-z`, `0-9`,
`-`, starting with a letter). Each stack is Compose project `ai-platform-poc-<stack>` with `docker/poc.override.yml`:
no fixed container names, no database host ports, and only the API published, on `127.0.0.1` at the free port stored in
`.poc/<stack>/marker.json`. It never touches the developer project `ai-platform` or its volumes.

`up` builds the one app image used by the API and worker, writes `.poc/<stack>/release-manifest.json` (every external
image proven to be a multi-arch index, the local build identified as `local-build`), creates the database and the
`gap_app` role, migrates as the owner role, then starts the API and worker as `gap_app` with a read-only root, no
capabilities and no privilege escalation. A repeat `up` changes nothing. The identity `up` compares is `content_id`: the
ordered layer digests plus the runtime config that changes behaviour (Entrypoint, Cmd, Env, User, WorkingDir,
ExposedPorts, Labels without the Compose-generated ones). The Docker store image ID is recorded as information only
("local store id (not stable across rebuilds)"): under the containerd image store it changes on every rebuild. If the
layers or config changed since the manifest was written, `up` refuses; run `up <stack> --refresh-release` after a
deliberate change. `up` needs the registry once, to
prove the image indexes. Docker must be the local engine (no `DOCKER_HOST` over TCP). Compose selection (`COMPOSE_*`) and optional profiles from
your environment are ignored, but `APP_DB_PASSWORD` and `POSTGRES_PASSWORD` are not: they reach Compose interpolation
(defaults `gap_app` and `postgres`). Set them the same on every `up` of a stack, because the database role keeps the
password it was created with. The stack never reads `.env` or `.env.local`.

### Backup, checked down, restore, destroy and the drill
All commands are `poetry run python scripts/poc <command> <stack>`.

| Command | What it does |
|---|---|
| `backup` | Online backup while the stack runs. Takes the shared backup lock, runs `pg_dump -Fc` inside the Postgres container, copies and hash-checks the referenced objects, writes its manifest (counts, chain heads, checkpoints, today's cost counters, public key id) and stores ONE restic snapshot. Prints `POC_RECOVERY_REF=<snapshot id>`. the `latest` pointer moves only after restic stored the snapshot; any failure publishes nothing. |
| `down` | Checked teardown. Needs `POC_RECOVERY_REF=<the latest snapshot id>`. It stops the API and worker, then checks in order: marker, the reference is the latest backup, live row counts, chain heads, checkpoints, schema head and object list equal the manifest (else "data written after backup; run poc backup"), the backup is not older than `POC_BACKUP_MAX_AGE_SECONDS` (default 86400), then `restic check --read-data` and a scratch restore. Only then are the containers and the marker-listed volumes removed. Any refusal restarts the services and removes nothing. The receipt key, repository password, backups and marker are kept. |
| `up` after `down` | Sees the marker, a published backup and no runtime volumes, so it restores before any writer starts: verifies the manifest, loads the dump into an empty database, copies the objects, compares counts, heads and checkpoints, re-applies same-UTC-day cost counters with `INCRBY`, then starts the API and worker. It prints `RESTORED ...` and what an empty Valkey lost (rate-limit windows, cache, sessions, token counters, breaker state, leases). Queued jobs, leases and the outbox are in Postgres and resume. |
| `up <stack> --create-only` | The atomic "I am the creator" form of `up`. Under the lifecycle lock it refuses (exit 2) when any state of the stack exists (a `.poc/<stack>` folder or runtime volumes), and otherwise records `POC_OWNER_TOKEN` (32 to 64 lowercase hex characters, from the environment, never argv) in `.poc/<stack>/owner.token` before anything else. A plain `up` writes no token. |
| `status [--json]` | Non-secret facts: services, the latest backup (id, age, counts, heads, checkpoints), the last restore report, a pending restore. Exit 3 means no `.poc/<stack>` folder exists at all; any other nonzero exit is a failed probe (remote Docker, unsafe folder, no marker), not proof of absence. |
| `admin <stack> <command> ...` | The identity and policy CLI (`create-principal`, `create-key`, `set-policy <tenant> -` with the policy on stdin, ...) against the stack's own database, run in the app image. `--dsn` is refused. |
| `destroy <stack> --confirm <stack>` | The explicit, total end: containers, runtime and scratch volumes, the two built images, then the whole `.poc/<stack>` folder including the key and every backup. Refuses a foreign volume or a symlinked folder, and anything while another lifecycle command holds the lock; it holds that lock until the folder is gone. With `POC_OWNER_TOKEN` set it removes only a stack whose `owner.token` matches (a stack made without `--create-only` is refused). Not reversible. |

**Restore-pending marker.** `up` writes `.poc/<stack>/restore-pending.json` (snapshot id and manifest digest) before any new runtime volume exists and clears it only after the restored data verified, before the writers start. While it exists `up` never migrates an empty database: it resumes the restore from the same snapshot, after removing only this stack's partial volumes. `backup`, `down` and `admin` refuse while it exists, so `latest` can never move to a partial state. `status` shows it.

**Lock behaviour.** One lifecycle command (`up`, `backup`, `down`, `destroy`) per stack at a time. `up` WAITS for the lock (it blocks, then decides on the state the holder left); `backup`, `down` and `destroy` REFUSE at once with "another lifecycle command ... is running" if it is held. The lock file is `.poc/.locks/<stack>.lock`, outside the stack folder, so `destroy` keeps the lock through every deletion and a waiting `up` never sees half-deleted secrets or backups. A backup also holds a Postgres advisory lock. The retention purge takes the same key shared, waits at most 30 s, and on a timeout is deferred, not failed: the job goes back to `queued` for later (at least 1 s, 60 s for purge), the attempt is not used, and `jobs.deferrals` counts it (visible on the job and in the worker log). A backup that loses its lock session before it publishes fails and moves nothing.

**Compose API port.** A POC stack publishes only the API, on `127.0.0.1:<port>` from the stack marker. The developer project's `api` service also wants `127.0.0.1:8000`; run only one of them there, or set `API_HOST_PORT`.

The backup profile builds restic 0.19.1 from the checksum-verified source in `docker/restic`. Compose builds the local image on its first run; subsequent backup and restore operations use the local image offline.

**TMPDIR.** `api` and `worker` spool uploads to `TMPDIR=/var/tmp/app` (volume `app_tmp`, scratch only, removed by `destroy`). On the host, restic restore and the scratch directories live under `.poc/<stack>/`; make sure the disk holding the repository has room for one dump plus the objects, and set `TMPDIR` for `poc` itself only if `/tmp` is small.

**The drill.** `bash scripts/verify/poc-drill.sh <stack>` (also the last step of `scripts/showcase/m0.sh [stack]`, default `m0drill`) runs the whole journey on a fixture stack it creates itself: a status probe (exit 3 = absent; any other nonzero exit aborts, a stack that exists is never adopted), `up --create-only` with a fresh owner token, seed an operator and an auditor, publish a policy that omits the chat alias, and make one governed search that must be denied with exactly `model_not_allowed` (any other reason, including `model_digest_mismatch`, fails). The stack is pointed (`POC_OLLAMA_BASE_URL`, set on every `up`) at a metadata-only runtime the drill starts on the host: it lists the reviewed digests from `models.lock`, so the alias resolves, and it refuses and counts every inference request. The drill requires the signed receipt to carry the alias and the `admission` phase (a missing phase fails), and an observed zero: no inference request at that runtime and `totals.requests` 0 in `/v1/usage/summary`. Then it saves the receipt and public keys, restores the baseline policy, backs up, checked down, restores, compares the restored counts and chain heads with the backup before any new traffic, verifies the saved receipt offline, makes a new governed deny with the same checks, and destroys the fixture with the owner token (a stack it did not create is refused). It uses only `poc` commands, the public API and `scripts/verify/receipt.py`. It prints one `PASS <step>` or `FAIL <step>` line per step and never SKIP. To point your own stack at Ollama on the host, set `POC_OLLAMA_BASE_URL=http://host.docker.internal:11434` on `up` (Ollama must listen beyond loopback). `up` validates it (http or https, a host, no credentials) and stores it, not secret, in `.poc/<stack>/ollama-base-url` (0600), so a later `up` without it and a `down` that restarts the writers after a refusal use the same URL; a value in the environment still wins, and the next `up` stores it.
