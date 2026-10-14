# Sprint 012: Builder brief
You are the Builder for Sprint 012 in /home/ubuntu/ai-platform, on branch `sprint/012-open-source-stack`. Infrastructure: compose, CI services, the cache adapter and verify scripts. No API, schema or UI change. Work autonomously. Stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. On one, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`.
- This folder: `requirements.md`, `blueprint.md`, `acceptance.md`, `threat-model.md`.
- `planning/program/stack.md` (pins, memory budget) and the Sprint 011 report.
- `adapters/redis_cache.py`, `tests/contracts/test_cache_contract.py`, `tests/contracts/test_object_store_contract.py`, `scripts/verify/kafka.sh`, `scripts/verify/minio.sh`, `docker-compose.yml`, `.github/workflows/`.

## Build
Start with the Valkey spike: run the cache contract suite on `valkey/valkey-bundle:9.1.3` before you change compose. Then Kafka, SeaweedFS, compose, preflight, docs. Write a short plan in `build-log.md` first.

## Tests
- **Baseline:** the numbers in Sprint 011's report.
- Cache contract on Valkey in the normal suite (CI runs Valkey as its service).
- Kafka and SeaweedFS live runs go in `scripts/verify/kafka.sh` and `scripts/verify/seaweedfs.sh` and their evidence, never in a skipped pytest. The pytest suite keeps the in-memory Kafka fake and the fake S3 client.
- The live S3 parameter replaces the MinIO one, so the skip count stays the same. Update `tests/skip_allowlist.json` and state the count in the report.

## Notes from the Architect
- **Code facts:**
  - `ensure_semantic_index` matches the text "Index already exists". Valkey says "Index <name> in database 0 already exists". Match "already exists".
  - `_ft_create` indexes `response` and `query` as TEXT. Nothing searches them. `semantic_lookup` sends `SORTBY score` after a KNN query that is already sorted.
  - Compose today: `redis/redis-stack-server` on `6379:6379` and Postgres on `5432:5432`, both on all interfaces; `ollama` has no profile and publishes `11434:11434`; the `kafka` profile runs Redpanda (`redpanda`, `kafka-topics` services, `rpk`).
  - `scripts/verify/kafka.sh` uses `--profile kafka` and the container name `redpanda`.
  - The live object store parameter is `minio`, read from `MINIO_*` variables, with the skip reason "live MinIO not available".
- **Pins:** `valkey/valkey-bundle:9.1.3`, `redis==8.1.0`, `apache/kafka:4.3.1`, `chrislusf/seaweedfs:4.47`. Re-check and save tag, digest and source in `evidence/pins.txt`. Run the licence gate after the lock change.
- **Valkey fallback:** take it only if the spike fails. Then build `adapters/pg_semantic_cache.py` behind the same port, add it to the cache contract suite, and record the reason in `evidence/valkey-spike.txt`.
- **Old volume:** do not delete `redis_data`. Use the new `valkey_data` volume. Document how a user removes the old one.
- **Kafka in KRaft mode:** one node with combined broker and controller roles; a fixed cluster id in compose. No SASL yet (020).
- **Ollama:** the pull job pulls only `nomic-embed-text:v1.5` here. Sprint 014 adds the chat models and `models.lock`.
- **No migration** unless the fallback is taken. Then it takes the next free number after the previous sprint's head (0010 at the start of 011).

## Run
```bash
scripts/preflight.sh
docker compose up -d postgres valkey && scripts/setup_db.sh
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/docs
poetry run mypy
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/012-open-source-stack/evidence/pytest-int-e2e.xml
poetry run python scripts/check_skips.py planning/sprints/012-open-source-stack/evidence/pytest-int-e2e.xml
scripts/supply_chain/licence_gate.sh
scripts/verify/kafka.sh
scripts/verify/seaweedfs.sh
for p in "" models cdc lake observability; do docker compose ${p:+--profile $p} config -q && echo "ok $p"; done
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. S3 keys and passwords come from the environment.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1 to A7, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against Sprint 011's report
- migrations ("none", or the fallback migration)
- measured memory per new service
- deviations and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`: code (`adapters/redis_cache.py`, `core/settings.py`, `feat(adapters)`), tests (`test(adapters)`), ops (`docker-compose.yml`, `.github/`, `scripts/`, `chore(ops)`), docs (`docs(ops)`), planning (`docs(planning)`), each with its `git add` paths, then the push and `gh pr create --base main` commands.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.
