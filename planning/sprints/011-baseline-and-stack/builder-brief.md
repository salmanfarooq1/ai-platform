# Sprint 011: Builder brief
You are the Builder for Sprint 011 in /home/ubuntu/ai-platform, on branch `sprint/011-baseline-and-stack`, created locally from `planning/sprint-plans` (`git switch planning/sprint-plans && git switch -c sprint/011-baseline-and-stack`). Everything is local: do not pull, push or switch to `main`, and leave untracked files at the repo root alone. The work covers infrastructure plus the bounded MCP compatibility and font/animation dependency changes selected in `architect-disposition.md`. There is no route or API contract change; only the documented cache fallback may require a migration.

Work autonomously. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or spending money. When one happens, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

This sprint has two parts. Follow `architect-disposition.md`: replacement work may proceed while superseded dependency gates are red. Record part-a results honestly, then complete part b and run every check against the final stack. All gates must pass before sprint acceptance or Sprint 012 implementation. The bounded UI licence migration and exact-artifact audit in that disposition are selected scope amendments.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md` (top section: Program 2 direction).
- This folder: `requirements.md`, `blueprint.md` (the contract), `acceptance.md` and `threat-model.md`.
- `planning/program/stack.md` (pins, the two-week rule, memory budget) and `planning/program/branching-and-commits.md` (scope list, commit blocks).
- Part a: `core/settings.py`, `scripts/docs/check_links.py`, `scripts/check_skips.py`, `.github/workflows/`, `docker-compose.yml` and `Dockerfile`.
- Part b: `adapters/redis_cache.py`, `tests/contracts/test_cache_contract.py`, `tests/contracts/test_object_store_contract.py`, `scripts/verify/kafka.sh`, `scripts/verify/minio.sh`, `adapters/pg_knowledge.py` and `api/services/retriever.py`.

## Build
- **Part a**, in this order: planning drift, the two bugs, pins, skip allowlist, supply chain scripts, the LiteLLM check, CI.
- **Part b:** start with the Valkey spike. Run the cache contract suite on `valkey/valkey-bundle` before you change compose. Then Kafka, SeaweedFS, compose, preflight, the keyword-search naming and the docs.
- Write a short plan in `build-log.md` before each part.

## Tests
- **Baseline:** 1568 backend passed and 10 skipped (live MinIO), 207 Vitest, 82 Playwright.
- Counts may only grow by the new tests. No skip is added. The live S3 parameter replaces the MinIO one, so the skip count stays the same.
- Each acceptance item has a named test or command.
- Kafka and SeaweedFS live runs go in their verify scripts and evidence, never in a skipped pytest. The pytest suite keeps the in-memory Kafka fake and the fake S3 client.

## Notes from the Architect
- **Code facts, part a:**
  - `_load_env_files` in `core/settings.py` uses `override=True` for `.env.local` only. `.env` already loads without override.
  - `scripts/docs/check_links.py` walks `root.rglob("*")` in `_known_names` and `doc_files`. Ask git for ignored paths once (`git ls-files --others --ignored --exclude-standard --directory`) and drop them. Outside a git checkout, skip nothing.
  - `scripts/check_skips.py` hard-codes `ALLOWED_CLASS` and `ALLOWED_REASON`. The JUnit class is `tests.contracts.test_object_store_contract`, the name holds `[minio`, and the reason starts `live MinIO not available`.
  - CI installs Poetry with `pipx install poetry` (no pin) and caches `~/.cache/pypoetry`, not `.venv`. The secret scan uses `gitleaks/gitleaks-action@v2` with `GITHUB_TOKEN`.
  - The CI ruff line also covers `scripts/docs`.
  - `.gitleaksignore` holds two reviewed false positives (commit `8dc31ab`). Keep them.
  - The `ollama` compose service has no tag and no profile. Pin it in part a and move it to a profile in part b.
- **Code facts, part b:**
  - `ensure_semantic_index` matches the text "Index already exists". Valkey says "Index <name> in database 0 already exists". Match "already exists".
  - `_ft_create` indexes `response` and `query` as TEXT. Nothing searches them. `semantic_lookup` sends `SORTBY score` after a KNN query that is already sorted.
  - Compose today:
    - `redis/redis-stack-server` on `6379:6379` and Postgres on `5432:5432`, both on all interfaces.
    - `ollama` publishes `11434:11434`.
    - The `kafka` profile runs Redpanda (`redpanda` and `kafka-topics` services, `rpk`).
  - `scripts/verify/kafka.sh` uses `--profile kafka` and the container name `redpanda`.
  - The live object store parameter is `minio`, read from `MINIO_*` variables, with the skip reason "live MinIO not available".
  - Keyword search:
    - `search_bm25` in `adapters/pg_knowledge.py` ranks with `ts_rank(fts_vector, ...)`.
    - The API exposes `bm25_only` (`api/models/schemas.py`) and `bm25_score` (`api/routers/search.py`, `api/mcp/tools.py`).
    - Do not rename public values. Comments and docs only.
- **Pins:** take them from `planning/program/stack.md`. Re-check each one and save the tag, digest, release date and source in `evidence/pins.txt`. A pin younger than two weeks at sprint start is replaced by the previous release. Tool pins marked UNV (gitleaks, osv-scanner or grype) are chosen here and saved the same way.
- **Licence gate:**
  - Allow only OSI ids. Grafana is AGPL-3.0 (OSI) and runs only in an optional profile. LGPL and MPL are OSI.
  - If a current dependency fails, do not widen the allowlist with a non-OSI id. Log it in `planning/QUESTIONS.md`, and add it to `licence-exceptions.txt` only when the real licence is OSI.
- **LiteLLM:**
  - The licence comes from the wheel we lock, not from a blog.
  - The incident check uses the project's own advisories or release notes. If you cannot find a primary source, write "not found" and the searches you made.
  - Do not upgrade or downgrade LiteLLM in this sprint unless our version is affected. In that case, stop the item and raise a blocker.
- **Path filters** must never skip a required check silently. Use a filter job whose result the required jobs read, or keep required jobs unfiltered.
- **Valkey fallback:**
  - Take it only if the spike fails. Then build `adapters/pg_semantic_cache.py` behind the same port, add it to the cache contract suite, and record the reason in `evidence/valkey-spike.txt`.
  - The fallback migration takes the next free number after `0010`.
- **Old volume:** do not delete `redis_data`. Use the new `valkey_data` volume. Document how a user removes the old one.
- **Kafka:**
  - KRaft, one node with combined broker and controller roles, and a fixed cluster id in compose. No SASL yet (022).
  - The profile is `streams`. The outbox stays the default.
- **Ollama:** the pull job pulls only `nomic-embed-text:v1.5`. Sprint 013 adds the chat models and `models.lock`.

## Run
```bash
scripts/preflight.sh                      # part b onward
docker compose up -d postgres valkey && scripts/setup_db.sh   # part a: postgres redis
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain
poetry run mypy
scripts/check_no_ddl.sh
poetry run pytest -m unit -q
poetry run pytest -m "integration or e2e" -q -rs --junitxml=planning/sprints/011-baseline-and-stack/evidence/pytest-int-e2e-<a|b>.xml
poetry run python scripts/check_skips.py planning/sprints/011-baseline-and-stack/evidence/pytest-int-e2e-<a|b>.xml
scripts/supply_chain/export_locks.sh --check
scripts/supply_chain/licence_gate.sh
scripts/supply_chain/licence_gate.sh --fixture tests/fixtures/licence/non_osi   # must fail
scripts/supply_chain/sbom.sh
gitleaks git --redact --no-banner .
scripts/verify/kafka.sh                   # part b
scripts/verify/seaweedfs.sh               # part b
for p in "" models streams lake observability; do docker compose ${p:+--profile $p} config -q && echo "ok $p"; done
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check
cd ui && npm run e2e
```
Never run `playwright install`.

## Rules
- Never weaken, skip or delete a test to get green.
- No secrets in files or logs. Refer to them by env var name. S3 keys and passwords come from the environment.
- The hosted mode is called `public-preview` and nothing else. No brand name for the platform. No model or tool attribution in any file.
- Short, plain sentences in docs.
- Never commit or push.

## Finish
Write `report.md` with:
- the acceptance table (A1–A8, B1–B8, A-sec, A-mem) with links to `evidence/`
- test numbers and the delta against the baseline, per part
- migrations: "none", or the fallback migration
- measured memory per new service
- the LiteLLM result
- deviations from the blueprint, and open questions (also in `planning/QUESTIONS.md`)
- proposed commit blocks per `planning/program/branching-and-commits.md`, each with its `git add` paths. Messages are plain and functional (`type(scope): summary`), with no framing words:
  - code: `core/settings.py`, `scripts/docs/`, `scripts/check_skips.py`, `adapters/redis_cache.py`, `fix(core)` and `feat(adapters)`
  - tests: `test(ci)` and `test(adapters)`
  - ops: `.github/`, `docker-compose.yml`, `Dockerfile`, `scripts/`, `requirements/`, `ci(ops)` and `chore(ops)`
  - docs: `docs(ops)`
  - planning: `planning/` and `CHANGELOG.md`, `docs(planning)`
- no push or pull request commands. The owner pushes after the Architect's review.

Update `planning/STATE.md` and `CHANGELOG.md`. Do not commit.

## Selected MCP compatibility amendment
The Architect review authorizes only the expected-error compatibility work for MCP 2.2.0 inside `api/mcp/`. Translate known `GatewayDenied` results to the SDK expected tool/resource error types using controlled reason codes. Preserve route shapes, schemas, denial reasons, gateway enforcement and input-guardrail JSON. Unexpected exceptions must retain SDK masking and must not expose exception text in responses or application logs. Add a sentinel-secret regression and retain the existing policy-denial and concurrent-reply assertions. This bounded amendment does not authorize a transport redesign, UI changes or part b.

## Template location clarification
Keep the reusable template in this sprint as `threat-model-template.md`. This reconciles the shared-template request with the owner's folder restriction; do not modify `_template` or any other sprint folder.
