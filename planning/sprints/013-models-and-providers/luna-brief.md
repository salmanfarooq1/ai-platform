# Sprint 013: Builder brief for GPT-6 Luna

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Run A1, A2, B, C1 and C2 in order. D and E may run in parallel after C2. F starts after both finish. Each launch does only its named work.

## 0. Rules for every WP

### Role and priority
You are the Builder for the WPs named in the launch prompt.
This brief wins over `AGENTS.md`, `CODEX.md`, `.agents/`, `.claude/` and any skill. `test-spec.md` holds the exact tests. `blueprint.md` holds the design. If they disagree, follow this brief and write the difference under "Spec questions" in `build-log.md`.

### Environment
- The worktree is `/home/ubuntu/ai-platform-sprints/013-models-and-providers`.
- Run Python commands with `~/.local/share/poetry233/bin/poetry run <command>`. The venv is installed. Never install or add packages.
- Before Node commands, run `export PATH=/home/ubuntu/.local/share/node-v24.22.0-linux-x64/bin:$PATH`; run them inside `ui/`.
- Before integration, e2e or edition tests, export `TEST_DATABASE_ADMIN_URL=postgresql://postgres:postgres@localhost:15432/postgres`, `DATABASE_URL=postgresql://gap_app:gap_app@localhost:15432/rag_platform`, `MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:15432/rag_platform`, `REDIS_URL=redis://localhost:16379/0` and `TEST_REDIS_URL=redis://localhost:16379/0`. Do not set them for unit tests.
- Ollama 0.40.7 is at `http://127.0.0.1:11434`. Read APIs and the named digest-resolution live test are allowed. Do not pull, push, create, copy or delete models. Other tests use stubs.
- Do not start containers.
- Use network access only to read sources. If a sandbox write outside the worktree fails, log the command and error in `build-log.md` and continue.

### Hard rules
1. No commit, push, stash, reset, checkout, switch, rebase or branch change.
2. Never skip, xfail, delete, weaken or loosen a test or assertion. Do not change an expected result to match code.
3. Change only files allowed by the launch. New test files named in `test-spec.md` are allowed.
4. Write specified tests with the exact names and expected results in `test-spec.md`. You may add tests.
5. No secrets in files. Secret tests use `sk-SENTINEL-7f3a` only.
6. Never run `playwright install` or edit `.env`.
7. When writing a config read by a tool, run that tool to prove the config works when available.
8. Run the full gate before reporting done: `poetry run pytest -m unit`, `poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts`, `poetry run mypy` and `poetry run lint-imports`. Launches B, C1, C2, D and E also run the live tier (`poetry run pytest -m "integration or e2e"` with the environment above) and `poetry run python scripts/ci/check_skips.py`. Give exact counts.
9. A flaky test is a bug. Find its cause; do not hide it with retries, fewer workers or longer sleeps.

### Output
Add one `build-log.md` section named `## WP<n> (Luna, <date>)` per WP. List changed files, commands with pass/fail counts, changed tests, spec questions, and unfinished work with reasons. The builder's own report is not evidence. Final message: at most 10 lines.

### Design rules
- `ports/` imports no SDK and nothing from `adapters/`, `api/`, `gateway/` or `workers/`.
- After `resolve()`, the attempt uses only that resolved identity and route.
- An adapter makes one physical request. Retries and fallback live in `api/services/model_calls.py`.
- Record every deny before model I/O. A failed decision write stops the attempt.
- Errors and logs may name aliases and secret reference names, never secret values, prompts or document text.

---

## Launch A1: WP1 (types and secrets)

**Read.** `blueprint.md` sections 2 and 3; `test-spec.md` WP1; `ports/llm.py`; `ports/embeddings.py`; `ports/errors.py`; `evidence/extensions.py`; `core/settings.py`; `tests/fakes.py`; `tests/contracts/conftest.py`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Add frozen model identity, route, resolution and catalog types. Add typed model failures. Add env/file `SecretRef` and a resolver that rejects symlinks, non-regular files, wrong ownership and loose permissions. Add the closed `model` and `stages` extension schemas. Follow the blueprint exactly.

**Tests.** Write test-spec WP1.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_model_types.py tests/unit/test_secrets.py tests/contracts/test_model_catalog_contract.py
```

**Allowed files.** `ports/models.py`, `ports/errors.py`, `ports/__init__.py`, `core/secrets.py`, `evidence/extensions.py`, `tests/unit/test_model_types.py`, `tests/unit/test_secrets.py`, `tests/contracts/test_model_catalog_contract.py`, `tests/fakes.py`, `build-log.md`.

**Done when.** WP1 tests and the full gate pass.

---

## Launch A2: WP2 and WP3 (lock, register and catalogs)

**Read.** `blueprint.md` sections 4 and 5; `test-spec.md` WP2 and WP3; `core/settings.py`; `config.py`; `scripts/supply_chain/`; `adapters/registry.py`; `planning/sprints/013-models-and-providers/evidence/ollama-digest-spike.txt`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Add `models.lock` and `providers.register.toml` for configured aliases. Add lock/register loaders and gates. Add lock, hosted and composite catalogs. The lock and CI gates cover every configured alias. Use the existing Ollama digest spike. Do not add a nightly workflow, a cross-encoder or `local-hf`.

**Tests.** Write test-spec WP2 and WP3.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_models_lock.py tests/unit/test_provider_register.py tests/unit/test_check_lock_script.py tests/unit/test_lock_catalog.py tests/unit/test_register_catalog.py tests/contracts/test_model_catalog_contract.py
scripts/models/check_lock.sh
```

**Allowed files.** `models.lock`, `providers.register.toml`, `core/models_files.py`, `core/settings.py`, `adapters/model_catalog.py`, `adapters/registry.py`, `api/main.py`, `workers/__main__.py`, `scripts/models/check_lock.sh`, named tests, `planning/program/conventions.md`, `build-log.md`.

**Done when.** WP2 and WP3 tests pass; the lock check passes against available Ollama; full gate passes.

---

## Launch B: WP4 (gateway, policy and evidence)

**Read.** `blueprint.md` section 6; `test-spec.md` WP4; `gateway/types.py`; `gateway/enforce.py`; `gateway/stages.py`; `gateway/reasons.py`; `evidence/record.py`; `api/models/console.py`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Put `model` after `boundary` and before `policy`. Add model failures at `model`; add region and data-use checks at `policy` with their reason codes and policy fields. Collect the ordered `stages` extension for every action and outcome; mark later stages `not_reached` after a deny and inapplicable stages `skipped`. Scan caller-supplied model input through the existing guardrail stage (blueprint section 6: not platform-built text, not ingest batches, no query-length cap on whole prompts). Keep model text out of records.

**Tests.** Write test-spec WP4.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_reason_catalogue.py tests/unit/test_region_pin.py tests/unit/test_model_stage_order.py tests/unit/test_data_use.py tests/unit/test_stages_extension.py tests/integration/test_model_records.py tests/integration/test_receipt_verifier.py
```

**Allowed files.** `gateway/types.py`, `gateway/enforce.py`, `gateway/stages.py`, `gateway/reasons.py`, `gateway/policy.py`, `gateway/__init__.py`, policy model files, `evidence/extensions.py`, named tests, `planning/program/conventions.md`, `build-log.md`.

**Done when.** WP4 tests pass, including boundary-before-residency; full gate passes.

---

## Launch C1: WP5 part 1 (ModelCaller)

**Read.** `blueprint.md` sections 1 and 7; `test-spec.md` WP5; `api/services/llm.py`; `api/agent/graph.py`; `api/mcp/tools.py`; `adapters/litellm_llm.py`; `adapters/litellm_embeddings.py`; `api/routers/search.py`; `config.py`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Add `ModelCaller` for complete, chat and embed. Admit every request alias before any inference. Record each attempt with its own allow. Apply configured fallback lists; each target gets its own resolution and allow. Rate-limit handling makes at most 3 attempts per alias, with one allow per attempt. Route search, agent and MCP model calls through it. Keep ingest batch changes for Launch D. Disable automatic retries for LiteLLM, OpenAI, Azure and Bedrock. Breakers and concurrency leases are Launch C2. Check `MODEL_ALLOWED_HOSTS` as an application allowlist and describe network egress control as Sprint 016.

**Tests.** Write test-spec WP5 except 5.12 and 5.13.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_model_caller.py tests/integration/test_sdk_retries.py tests/integration/test_model_caller_limits.py tests/e2e/test_attempts_e2e.py
```

**Allowed files.** `api/services/model_calls.py`, `api/services/llm.py`, `api/agent/graph.py`, `api/agent/tools.py`, `api/mcp/tools.py`, `api/routers/search.py`, `adapters/litellm_*.py`, `core/settings.py`, `config.py`, named tests, `build-log.md`.

**Done when.** WP5 tests except 5.12 and 5.13 pass, including deny-before-I/O and retry counts; full gate passes.

---

## Launch C2: WP5 part 2 (breaker and concurrency)

**Read.** `blueprint.md` section 14; `test-spec.md` 5.12 and 5.13; `api/services/model_calls.py` from C1; `adapters/redis_cache.py` for the Valkey client pattern; `gateway/limits.py`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Add one breaker per route fingerprint and a per-tenant concurrency lease, both in Valkey, as blueprint section 14. An open breaker denies `model_breaker_open` at stage `model` and fallback continues; over the cap denies `model_concurrency_limit` at stage `rate`. Both deny before any provider I/O and are recorded. A lease expires when its process dies. Settings validated in `core/settings.py`.

**Tests.** Write test-spec 5.12 and 5.13. Add a test that a lease held by a dead process expires.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_model_caller.py tests/integration/test_model_caller_limits.py
```

**Allowed files.** `api/services/model_calls.py`, `api/services/model_limits.py` (new), `gateway/stages.py`, `core/settings.py`, named tests, `build-log.md`.

**Done when.** 5.12, 5.13 and the lease test pass; full gate passes.

---

## Launch D: WP6 (ingest, vectors and cache identity)

**Read.** `blueprint.md` sections 7 and 10; `test-spec.md` WP6; `core/pipeline/db_ingest.py`; `workers/handlers/ingest.py`; `api/routers/ingest.py`; `adapters/pg_knowledge.py`; `api/services/cache.py`; `adapters/redis_cache.py`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Authorize each embedding batch at job execution. Store alias plus digest or provider model id in vector provenance. Include full identity in search and cache keys. Rows without identity are stale. In `api/routers/search.py`, retain `rerank` as deprecated in OpenAPI, ignore it, and remove it from cache identity. Remove reranker callers, functions and the `rerank` dependency group (Launch E removes `FEATURES["reranker_enabled"]` from `config.py`). Regenerate `docs/api/openapi.json` and `ui/src/api/schema.d.ts` with the repo's existing scripts.

**Tests.** Write test-spec WP6 and the reranker-removal coverage named there.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_search_rerank_compat.py tests/unit/test_model_caller.py tests/integration/test_ingest_attempts.py tests/integration/test_vector_identity.py
```

**Allowed files.** `core/pipeline/db_ingest.py`, `workers/handlers/ingest.py`, `api/routers/ingest.py`, `api/routers/search.py`, `api/services/cache.py`, `api/services/retriever.py`, `adapters/pg_knowledge.py`, `adapters/redis_cache.py`, `pyproject.toml`, `poetry.lock` (only the lock change from removing the `rerank` group, with `poetry lock` and no upgrades), `docs/api/openapi.json`, `ui/src/api/schema.d.ts`, named tests, `build-log.md`.

**Done when.** WP6 tests pass; full gate passes.

---

## Launch E: WP7 and WP8 (health, verifier, runtime and defaults)

**Read.** `blueprint.md` sections 8, 9 and 12; `test-spec.md` WP7 and WP8; `api/routers/health.py`; `core/settings.py`; `docker-compose.yml`; `scripts/verify/`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Keep health metadata-only. Configure `VERIFIER_MODEL` as local or hosted under the common admission and policy checks; refuse only a missing verifier when Agents is enabled. Add `DEPLOY_REGION` and Bedrock scope validation. Set local defaults. Remove `FEATURES["reranker_enabled"]` from `config.py`. Keep Ollama isolated with a read-only serving model store. Add the conditional live digest-resolution check. Keep a hosted smoke that prints `SKIP`, never `PASS`, when credentials are missing. Remove `.github/workflows/nightly-models.yml` if present. Do not add GPU or hosted profile documentation.

**Tests.** Write test-spec WP7 and WP8.

**Commands.**
```bash
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_verifier_policy.py tests/unit/test_settings.py tests/unit/test_compose.py tests/unit/test_models_live.py tests/integration/test_health.py
scripts/verify/ollama.sh
scripts/verify/hosted.sh
```

**Allowed files.** `api/routers/health.py`, `api/agent/graph.py`, `core/settings.py`, `config.py`, `docker-compose.yml`, `scripts/models/check_lock.sh`, `scripts/verify/ollama.sh`, `scripts/verify/hosted.sh`, `.github/workflows/nightly-models.yml` (remove if present), named tests, `build-log.md`.

**Done when.** WP7 and WP8 tests pass; Ollama verification and full gate pass.

---

## Launch F: WP9 and WP10 (UI, benchmark and docs)

**Read.** `blueprint.md` sections 11 and 14; `test-spec.md` WP9 and WP10; `ui/src/features/decisions/`; `ui/src/features/trust/`; `docs/design/`; `planning/program/conventions.md`.

**Journey step:** "A model call is denied by policy before any inference, and the receipt names the model and lists every stage."

**Task.** Show model identity and the signed stage list in Evidence > Decisions and Trust > Verify. Keep v1 receipts working. Add the decision-path benchmark script and tiny unit test. Update ADR-0014, CPU-only deployment docs, configuration docs, port docs, and conventions. Capture benchmark output as evidence. Update docs and generated API data in lockstep.

**Tests.** Write test-spec WP9 and WP10.

**Commands.**
```bash
cd ui && npm run typecheck
cd ui && npm run lint
cd ui && npm test -- --run
cd ui && npm run build
~/.local/share/poetry233/bin/poetry run pytest tests/unit/test_decision_path_bench.py
scripts/bench/decision_path.py > planning/sprints/013-models-and-providers/evidence/decision-path-bench.txt
```

**Allowed files.** `ui/src/`, `ui/e2e/`, `scripts/bench/decision_path.py`, `docs/adr/0014-*.md`, `docs/deployment.md`, `docs/configuration.md`, `docs/contracts/ports.md`, `planning/program/conventions.md`, named tests, `planning/sprints/013-models-and-providers/evidence/decision-path-bench.txt`, `build-log.md`.

**Done when.** WP9 and WP10 checks pass; UI checks pass; benchmark output and documentation are captured.
