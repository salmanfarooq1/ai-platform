# Sprint 012: Builder brief for GPT-6 Luna

The Architect wrote this brief on 2026-10-28. Every launch does one work package (WP). The launch prompt names it.

## 0. Rules for every WP

### Role and priority
You are the Builder for the WP named in the launch prompt. Do that WP only.
This brief wins over `AGENTS.md`, `CODEX.md`, `.agents/`, `.claude/` and any skill. Where they disagree, follow this brief.
`test-spec.md` in this folder holds the exact tests. `blueprint.md` and `architect-disposition.md` hold the design. If this brief and the blueprint disagree, follow this brief and write the difference under "Spec questions" in `build-log.md`.

### Environment
- The working folder is this worktree: `/home/ubuntu/ai-platform-sprints/012-pillars-and-boundaries`.
- Python: always run `~/.local/share/poetry233/bin/poetry run <command>`. The venv is already installed. Never run `poetry install`, `poetry add`, `poetry lock` or `pip`.
- Node: run `export PATH=/home/ubuntu/.local/share/node-v24.22.0-linux-x64/bin:$PATH` before any `npm` or `npx` command. Run them inside `ui/`.
- Live tiers: export these before any integration, e2e or edition test:
  ```
  export TEST_DATABASE_ADMIN_URL=postgresql://postgres:postgres@localhost:15432/postgres
  export DATABASE_URL=postgresql://gap_app:gap_app@localhost:15432/rag_platform
  export MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:15432/rag_platform
  export REDIS_URL=redis://localhost:16379/0
  export TEST_REDIS_URL=redis://localhost:16379/0
  ```
  Do not export them for the unit tier. Two unit tests in `tests/unit/test_settings.py` read `DATABASE_URL` and fail when it is set.
- If Postgres or Valkey cannot be reached (the tests skip with "is not reachable"), write that in `build-log.md` and go on with the unit tier. The Architect runs the live tiers.
- If a command fails because the sandbox blocks a write outside the worktree, write the command and the error in `build-log.md` and go on.
- You have no Docker. Never try to start containers.

### Hard rules
1. No `git commit`, `push`, `stash`, `reset`, `checkout`, `switch`, `rebase` or branch change.
2. Never add `skip`, `skipif`, `xfail` or `importorskip` to a test. Never delete a test. Never weaken, loosen or remove an assertion. Never change an expected value to match the code. If an old test now fails because of a behaviour this brief asks for, write the old and new assertion under "Changed tests" in `build-log.md` with the reason.
3. Change only the files the WP allows. A new test file that the WP names is allowed.
4. Write each specified test with the exact file, name and expected result from `test-spec.md`. You may add more tests.
5. No secrets, keys or passwords in any file. The local passwords above are the public dev defaults.
6. Never run `playwright install`. Never edit `.env`.
7. When a task writes a config read by a tool (import-linter, GitHub Actions, pytest markers), run that tool to prove the config works.

### Output
Add one section to `planning/sprints/012-pillars-and-boundaries/build-log.md` named `## WP<n> (Luna, <date>)`. It lists: the files changed, the commands run with their pass and fail counts, "Changed tests" (if any), "Spec questions" (if any), and what is not done and why.
Your final message is at most 10 lines: done, not done, and why.

---

## WP1: Live tiers and record v2 data tests
**Goal.** The integration and e2e tiers pass, and the migration and record v2 tests exist.

**Read.** `test-spec.md` (WP1), `tests/harness.py`, `tests/db_fixtures.py`, `migrations/versions/` (the 0011 file), `evidence/chain.py`, `scripts/verify/receipt.py`, `tests/unit/test_record_canonical.py`, `tests/integration/test_migration_0010.py` (pattern for upgrading from an older revision), `evidence/baseline-2026-10-28.txt`.

**Task.**
1. Run the live tiers (command below). Read every failure and error. The baseline file lists the ones the Architect saw.
2. Fix the cause in product code or in test fixtures. A test that needs two tenants uses `deploy_shape="multi_tenant"`, as `tests/db_fixtures.py::_make_tenant` does. Do not change what a test asserts.
3. Write tests 1.2, 1.3 and 1.4 in the new file `tests/integration/test_migration_record_v2.py`. Upgrade from revision `0010` the same way `test_migration_0010.py` upgrades from its older revision.
4. Write test 1.5 in the new file `tests/integration/test_record_v2.py`. Run the verifier as a subprocess: `python scripts/verify/receipt.py <file>` (read the script for its exact arguments).
5. Write test 1.6 in `tests/unit/test_record_canonical.py`.
6. Run the live tiers again until they pass. Then run the unit tier.

**Allowed files.** Product code under `api/`, `core/`, `gateway/`, `evidence/`, `ports/`, `adapters/`, `workers/` and `migrations/` only to fix a live-tier failure. `tests/db_fixtures.py`, `tests/harness.py`, `tests/conftest.py`, the two new test files, `tests/unit/test_record_canonical.py`, `build-log.md`.

**Tests.** 1.1 to 1.6 from `test-spec.md`, copied here:
- 1.1 whole integration and e2e tier: `pytest -m "integration or e2e" -rs` passes. The only skips are the 10 on the allowlist (`tests/skip_allowlist.json`).
- 1.2 `tests/integration/test_migration_record_v2.py::test_upgrade_keeps_v1_chain_and_adds_v2`: given a database at revision 0010 with 3 chained decision rows for one tenant; when it upgrades to 0011; then the 3 rows have `record_version=1` and `extensions='{}'`, a new decision through `PgDecisionSink` gets `record_version=2`, and chain verification over all 4 rows passes.
- 1.3 `tests/integration/test_migration_record_v2.py::test_v1_row_with_extensions_is_rejected_by_the_database`: after the upgrade, an owner-role UPDATE that sets `extensions='{"x":1}'` on a v1 row fails with a check violation.
- 1.4 `tests/integration/test_migration_record_v2.py::test_old_unfiltered_claim_is_not_executable_by_app`: at head, `has_function_privilege('gap_app', 'jobs_claim(text, integer)', 'EXECUTE')` is false and the 3-argument version is true. PUBLIC has EXECUTE on neither.
- 1.5 `tests/integration/test_record_v2.py::test_mixed_chain_receipts_verify_offline`: one v1 row (inserted at revision 0010, then upgraded) and one v2 row in the same tenant chain. `GET /v1/receipts/{id}` for each, then `scripts/verify/receipt.py` verifies both offline (exit code 0). Changing one character of either receipt's decision makes it exit non-zero.
- 1.6 `tests/unit/test_record_canonical.py::test_extension_order_does_not_change_hash`: two v2 records that are equal except for the insertion order of the same extension keys (use a schema registered in the test, as `test_schema_validation_and_owned_result` does) give the same `compute_row_hash`.

**Commands.**
```
~/.local/share/poetry233/bin/poetry run pytest -m "integration or e2e" -q -rs -p no:cacheprovider --junitxml=/tmp/wp1-live.xml
~/.local/share/poetry233/bin/poetry run python scripts/check_skips.py /tmp/wp1-live.xml
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
```
(Export the live-tier variables before the first command only.)

**Done when.** The live tiers have 0 failed and 0 errors. `check_skips.py` exits 0. The unit tier has 0 failed. Tests 1.2 to 1.6 exist with these names and pass.

---

## WP2: Composition boundary
**Goal.** Ingest always runs. The agent job handler is built only by `api.agent.jobs`. Agent and MCP code import only the `gateway` package API. (Findings R1, R2, R10.)

**Read.** `workers/context.py`, `workers/__main__.py`, `workers/embedded.py`, `core/modules.py`, `gateway/__init__.py`, `api/agent/graph.py`, `api/agent/response.py`, `api/agent/router.py`, `api/agent/tools.py`, `api/mcp/server.py`, `api/mcp/tools.py`, `api/mcp/transport.py`, `core/database/jobs.py`, `tests/fakes.py`.

**Task.**
1. Create `api/agent/jobs.py` with `build_agent_job_handlers(adapters, pool, gateway_runtime, settings, *, agent_graph=None, keyring=None, sandbox_driver=None) -> dict[str, Handler]`. Move `_since_claim`, `_finish_agent_run` and the body of the current `if "agents" in active.enabled_module_names:` block from `workers/context.py` into it. It returns `{KIND_AGENT_RUN: <handler>}`.
2. In `workers/context.py::build_handlers`: register `KIND_PURGE` and `KIND_INGEST` always. Then, for each module in `core.modules.MODULES` that is in `settings.enabled_module_names`, and for each dotted path in its `job_handlers` field (format `"package.module:function"`), import it with `importlib` and call it with the arguments of step 1. Merge the result. Raise `RuntimeError` if two handlers claim the same kind. Keep the signature of `build_handlers` as it is. `workers/context.py` must no longer contain the text `api.agent`.
3. Export these names from `gateway/__init__.py` and add them to `__all__`: `estimate_tokens` (from `gateway.estimate`), `record_cost` and `record_usage` (from `gateway.limits`), `LIMITED_PATHS` (from `gateway.limits`), `REASONS` (from `gateway.reasons`).
4. Change these imports to `from gateway import ...`:
   - `api/agent/graph.py`: `from gateway.estimate import estimate_tokens`
   - `api/agent/response.py`: `from gateway.limits import record_cost` and `from gateway.limits import record_usage as book_tokens`
   - `api/agent/router.py`: `from gateway.estimate import estimate_tokens`
   - `api/agent/tools.py`: `from gateway.estimate import estimate_tokens`
   - `api/mcp/server.py`: `from gateway.reasons import REASONS`
   - `api/mcp/tools.py`: `from gateway.estimate import estimate_tokens`
   - `api/mcp/transport.py`: `from gateway.limits import LIMITED_PATHS`
5. `Worker` already claims only the kinds in its handler map (`workers/loop.py:106`). Do not change `workers/loop.py`.
6. Write tests 2.1 to 2.5.

**Allowed files.** `api/agent/jobs.py` (new), `workers/context.py`, `gateway/__init__.py`, the seven files in step 4, `tests/unit/test_worker_handlers.py` (new), `tests/unit/test_gateway_package_api.py` (new), `tests/integration/test_module_disabled.py`, `build-log.md`.

**Tests.** From `test-spec.md`:
- 2.1 `tests/unit/test_worker_handlers.py::test_gateway_edition_registers_ingest_and_purge_only`: `build_handlers` with `ENABLED_MODULES=gateway` returns exactly the keys `{"ingest", "purge_decisions"}`.
- 2.2 `tests/unit/test_worker_handlers.py::test_agents_edition_adds_agent_run`: with `gateway,agents` the keys are exactly `{"ingest", "purge_decisions", "agent_run"}`. Pass `agent_graph=object()` so no real graph is built.
- 2.3 `tests/unit/test_worker_handlers.py::test_worker_context_imports_no_agent_code`: a fresh `python -c` subprocess that imports `workers.context` and calls `build_handlers` with `ENABLED_MODULES=gateway` (fakes) ends with no `api.agent`, `api.mcp`, `sandbox_agent`, `langgraph` or `openshell` module in `sys.modules`.
- 2.4 `tests/unit/test_gateway_package_api.py::test_agent_and_mcp_import_only_the_gateway_package`: an AST scan of `api/agent/**`, `api/mcp/**` and `sandbox_agent/**` finds no `from gateway.<x> import` and no `import gateway.<x>`. Only `from gateway import ...` is allowed.
- 2.5 `tests/integration/test_module_disabled.py::test_worker_does_not_claim_disabled_job_kinds`: queue one `agent_run` job and one expired-lease `agent_run` job, plus one `ingest` job. Run one worker with `ENABLED_MODULES=gateway` until it is idle. The ingest job reaches `succeeded`. Both agent jobs keep their exact status, attempts and lease.

Build `Settings` in unit tests with `Settings(_env_file=None, enabled_modules="gateway")` (or `"gateway,agents"`). Use the fakes in `tests/fakes.py`. Unit tests must not need Postgres.

**Commands.**
```
~/.local/share/poetry233/bin/poetry run pytest -q -p no:cacheprovider tests/unit/test_worker_handlers.py tests/unit/test_gateway_package_api.py
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
~/.local/share/poetry233/bin/poetry run pytest -q -p no:cacheprovider tests/integration/test_module_disabled.py tests/integration/test_worker_process.py tests/e2e
~/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests
~/.local/share/poetry233/bin/poetry run mypy
```

**Done when.** Tests 2.1 to 2.5 pass. The unit tier, ruff and mypy pass. `grep -n "api.agent" workers/context.py` prints nothing. The integration command passes.

---

## WP3: Import contracts
**Goal.** import-linter runs in CI and enforces the module rules. (Finding R5.) `import-linter==2.15` is already pinned in the dev group and installed. Its docs: https://import-linter.readthedocs.io/en/stable/contract_types.html (contract type `forbidden`, option `allow_indirect_imports`).

**Task.**
1. Add this block to `pyproject.toml`, after the `[tool.mypy]` sections. The Architect ran it on this tree: five contracts pass and `agents-gateway-api-only` fails until WP2 is done.
   ```toml
   [tool.importlinter]
   root_packages = ["api", "core", "gateway", "evidence", "ports", "adapters", "workers", "sandbox_agent"]

   [[tool.importlinter.contracts]]
   id = "ports-pure"
   name = "ports imports no platform package"
   type = "forbidden"
   source_modules = ["ports"]
   forbidden_modules = ["api", "core", "gateway", "evidence", "adapters", "workers", "sandbox_agent"]

   [[tool.importlinter.contracts]]
   id = "core-no-modules"
   name = "core imports no module package"
   type = "forbidden"
   source_modules = ["core"]
   forbidden_modules = ["api", "gateway", "evidence", "adapters", "workers", "sandbox_agent"]

   [[tool.importlinter.contracts]]
   id = "evidence-independent"
   name = "evidence does not import gateway, api or workers"
   type = "forbidden"
   source_modules = ["evidence"]
   forbidden_modules = ["gateway", "api", "workers"]

   [[tool.importlinter.contracts]]
   id = "gateway-independent"
   name = "gateway does not import evidence, api or workers"
   type = "forbidden"
   source_modules = ["gateway"]
   forbidden_modules = ["evidence", "api", "workers"]

   [[tool.importlinter.contracts]]
   id = "agents-no-evidence"
   name = "agent and MCP code do not import evidence"
   type = "forbidden"
   source_modules = ["api.agent", "api.mcp", "sandbox_agent"]
   forbidden_modules = ["evidence"]

   # gateway.enforce is not listed: import-linter reads `from gateway import enforce` (the function) as the
   # module gateway.enforce. tests/unit/test_gateway_package_api.py covers that module with an AST scan.
   [[tool.importlinter.contracts]]
   id = "agents-gateway-api-only"
   name = "agent and MCP code use only the gateway package API"
   type = "forbidden"
   source_modules = ["api.agent", "api.mcp", "sandbox_agent"]
   forbidden_modules = ["gateway.admin", "gateway.boundary", "gateway.context", "gateway.estimate", "gateway.guardrails", "gateway.limits", "gateway.module_stage", "gateway.policy", "gateway.reasons", "gateway.stages", "gateway.types"]
   allow_indirect_imports = true
   ```
2. If a later file adds a module under `gateway/`, it must be added to the last list. Write that as a comment above the list.
3. In `.github/workflows/tests.yml`, job `lint`: add `evidence` to the ruff command's package list, and add a step named `Check import contracts` that runs `poetry run lint-imports`.
4. Write tests 3.1 to 3.5 in the new file `tests/unit/test_import_contracts.py`. For 3.2 to 3.4, copy `pyproject.toml` and the eight root packages into `tmp_path` with `shutil.copytree` (ignore `__pycache__`), add the seeded line to a file in the copy, and run `lint-imports --config <tmp>/pyproject.toml` with `cwd=tmp_path`. Run the console script from the venv: `Path(sys.executable).with_name("lint-imports")`.

**Allowed files.** `pyproject.toml` (the `[tool.importlinter]` block only), `.github/workflows/tests.yml` (the lint job only), `tests/unit/test_import_contracts.py` (new), `build-log.md`.

**Tests.** From `test-spec.md`:
- 3.1 `tests/unit/test_import_contracts.py::test_tree_passes`: `lint-imports` on the repo exits 0.
- 3.2 `::test_seeded_violation_fails[from_gateway_policy]`: add `from gateway.policy import evaluate` to `api/agent/` code in the copy. `lint-imports` exits non-zero and its output names the contract.
- 3.3 `::test_seeded_violation_fails[from_gateway_import_policy]`: same with `from gateway import policy`. Exits non-zero.
- 3.4 `::test_seeded_violation_fails[evidence_imports_gateway]`: same with `import gateway` inside `evidence/`. Exits non-zero.
- 3.5 `::test_ci_lint_job_runs_lint_imports`: `.github/workflows/tests.yml`, job `lint`, has a step whose `run` is `poetry run lint-imports`.

**Commands.**
```
~/.local/share/poetry233/bin/poetry run lint-imports
~/.local/share/poetry233/bin/poetry run pytest -q -p no:cacheprovider tests/unit/test_import_contracts.py
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
~/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/ci
```

**Done when.** `lint-imports` prints "6 kept, 0 broken". Tests 3.1 to 3.5 pass. The unit tier and ruff pass.

---

## WP4: API contract and authority
**Goal.** Typed module metadata, record version in the API, and the authority tests. (Findings R3, R4, R11.)

**Read.** `api/routers/system.py`, `api/models/console.py`, `api/models/trust.py`, `api/routers/console.py` (`_DECISION_COLUMNS`, `_summary`, `fetch_decision_detail`), `core/modules.py`, `gateway/module_stage.py`, `gateway/boundary.py`, `api/module_routes.py`, `core/identity/deploy_shape.py`, `core/identity/admin.py`, `api/openapi.py`, `tests/integration/test_rls.py`, `tests/integration/test_run_tokens.py`.

**Task.**
1. Add to a new file `api/models/system.py`: `ModuleInfo` (fields `name: str`, `label: str`, `pillar: Literal["platform", "gateway", "data", "agents"]`, `enabled: bool`, `nav_group: str | None`, `always_on: bool`) and `ModuleList` (fields `edition: str | None`, `deploy_shape: Literal["single_tenant", "multi_tenant"]`, `modules: list[ModuleInfo]`). Set `response_model=ModuleList` on `GET /v1/system/modules` and return a `ModuleList`.
1b. Add `description: str` to `ModuleSpec` in `core/modules.py` (one plain sentence, at most 140 characters, saying what the module does for the user), include it in `module_metadata`, and add `description: str` to `ModuleInfo`.
2. Add `record_version: int` and `extensions: dict[str, Any]` to `DecisionDetail`. Select `d.record_version` and `d.extensions` in `fetch_decision_detail` and fill them. `Receipt.decision` is a `DecisionDetail`, so it gets them too. Do not change how `canonical` or the signature is computed.
3. Refresh the snapshot: `poetry run python scripts/update_openapi.py`.
4. Write tests 4.1 to 4.14. For 4.6, the two `run_bound=True` entries of `DISABLED_AGENT_ROUTES` authenticate with a run token, issued as in `tests/integration/test_run_tokens.py`. Every other entry uses an API key with the entry's first scope.
5. For 4.4, copy the pre-012 sets from `git show 555ca5f:gateway/boundary.py` (`SCOPE_ACTIONS`) into the test as literals. Reading git with `git show` is allowed.

**Allowed files.** `core/modules.py` (the `description` field only), `api/models/system.py` (new), `api/routers/system.py`, `api/models/console.py`, `api/routers/console.py`, `docs/api/openapi.json`, `ui/src/api/schema.d.ts` (regenerate with `npm run gen:api` in `ui/`), product code under `core/identity/` and `gateway/` only to fix a failing 4.x test, the test files named below, `build-log.md`.

**Tests.** From `test-spec.md`, 4.1 to 4.14, with these exact names:
- 4.1 `tests/unit/test_action_module_map.py::test_every_action_kind_maps_to_module`: every `ActionKind` member is a key in `ACTION_MODULES`, and each value is in `MODULE_NAMES`.
- 4.2 `tests/unit/test_action_module_map.py::test_modules_have_pillars`: every `ModuleSpec.pillar` is in `{"platform", "gateway", "data", "agents"}`.
- 4.3 `tests/integration/test_system_modules.py::test_each_single_scope_key_reads_metadata[<scope>]`: for each scope in `kb:read`, `kb:write`, `query`, `agent`, `audit:read` and `admin`, a key with only that scope gets 200 from `GET /v1/system/modules`. The body has `deploy_shape`, `edition` and `modules`, where every item has `name`, `label`, `pillar`, `enabled`, `nav_group` and `always_on`.
- 4.4 `tests/unit/test_system_read_scope.py::test_metadata_scope_grants_no_other_action[<scope>]`: for each scope, `build_boundary(principal_with_only_that_scope, None).actions` equals the pre-012 set for that scope plus only `"system.read"`.
- 4.5 `tests/integration/test_system_modules.py::test_no_credential_is_401_and_unknown_scope_is_403`: no header gives 401. A key whose stored scopes are empty gives 403.
- 4.6 `tests/integration/test_module_disabled.py::test_every_route_of_a_disabled_module_is_denied`: app with `ENABLED_MODULES=gateway`. For each entry of `DISABLED_AGENT_ROUTES`, an authenticated call answers 404 `module_disabled`, and exactly one deny row is added.
- 4.7 `tests/integration/test_module_disabled.py::test_deny_is_recorded`: `POST /v1/agent/query` with an `agent` key under `ENABLED_MODULES=gateway` gives 404 `module_disabled` and a deny row with `action='agent.run'`.
- 4.8 `tests/integration/test_module_disabled.py::test_missing_credential_or_scope_wins_over_module`: under `ENABLED_MODULES=gateway`, no credential on `POST /v1/agent/query` gives 401; a `query`-only key gives 403; neither adds a deny row with reason `module_disabled`.
- 4.9 `tests/unit/test_openapi_snapshot.py` (existing) passes, and the snapshot has `ModuleList`, and `DecisionDetail` has `record_version` (integer) and `extensions` (object).
- 4.10 `tests/integration/test_record_v2.py::test_api_shows_version_and_extensions`: `GET /v1/decisions/{id}` for a new decision returns `record_version: 2` and `extensions: {}`. For a v1 row it returns `record_version: 1` and `extensions: {}`.
- 4.11 `tests/integration/test_deploy_shape.py::test_single_tenant_startup_refuses_two_tenants`: database with two tenants; starting the app lifespan with `DEPLOY_SHAPE=single_tenant` raises `RuntimeError` that names `DEPLOY_SHAPE`. With `multi_tenant` it starts.
- 4.12 `tests/integration/test_deploy_shape.py::test_concurrent_second_tenant_creation_is_refused`: database with one tenant; two threads call `create_tenant(..., deploy_shape="single_tenant")` at the same time for two new slugs; both fail with `AdminError` and the tenant count stays 1. On an empty database, two concurrent creates give exactly one success.
- 4.13 `tests/integration/test_deploy_shape.py::test_probe_grants_and_search_path`: `deploy_shape_has_multiple_tenants()`: PUBLIC has no EXECUTE, `gap_app` has EXECUTE, `proconfig` sets a `search_path` that ends with `pg_temp`, and it returns a boolean. A `gap_app` session that creates `pg_temp.tenants` with 5 rows still gets the true answer.
- 4.14 `tests/integration/test_deploy_shape.py::test_rls_present_in_both_shapes`: with each shape, tenant A's key cannot read tenant B's documents or decisions (404 or an empty list, as the existing RLS tests expect).
- 4.15 `tests/unit/test_action_module_map.py::test_modules_have_descriptions`: every `ModuleSpec` has a non-empty `description` of at most 140 characters, and `GET /v1/system/modules` items carry it.

**Commands.**
```
~/.local/share/poetry233/bin/poetry run python scripts/update_openapi.py
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
~/.local/share/poetry233/bin/poetry run pytest -q -p no:cacheprovider tests/integration/test_system_modules.py tests/integration/test_module_disabled.py tests/integration/test_record_v2.py tests/integration/test_deploy_shape.py tests/integration/test_rls.py
~/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests
~/.local/share/poetry233/bin/poetry run mypy
```

**Done when.** Tests 4.1 to 4.15 pass with these names. The unit tier, ruff and mypy pass.

---

## WP5: Editions and the container
**Goal.** Each edition boots and passes its smoke set, in CI too. The image copies `evidence/`. (Findings R6, R9.)

**Task.**
1. Register the marker in `pyproject.toml` `[tool.pytest.ini_options].markers`: `"edition_smoke: boots one edition and runs its smoke set"`.
2. In `tests/conftest.py::pytest_collection_modifyitems`, mark items under `tests/editions/` with `edition_smoke` only (not unit, integration or e2e).
3. Write `tests/editions/test_edition_smoke.py::test_edition_smoke`. It reads `ENABLED_MODULES` from the environment, boots `create_app` with the real lifespan and the fake adapters (follow the e2e app fixture in `tests/db_fixtures.py` or `tests/e2e/conftest.py`), and runs the smoke set in `test-spec.md` (WP5).
4. Write `scripts/ci/edition_smoke.sh` (bash, `set -euo pipefail`, executable). It maps edition names to module lists from `core.modules.EDITIONS` (`Gateway`, `Assurance`, `Agents`, `Data`, `Full`). With no argument it runs all five; with one argument it runs that one. For each it runs `ENABLED_MODULES=<modules> poetry run pytest -m edition_smoke -q -p no:cacheprovider tests/editions`. It exits non-zero if any edition fails. An unknown edition name exits 2.
5. Write `.github/workflows/editions.yml`: trigger on `pull_request` and `push` to `main`; one job `smoke` with `strategy.matrix.edition: [Gateway, Assurance, Agents, Data, Full]`, Postgres and Valkey service containers with the same images and pinned digests as `docker-compose.yml`, the repo setup action (`./.github/actions/setup` with `groups: dev`), `scripts/setup_db.sh`, then `scripts/ci/edition_smoke.sh ${{ matrix.edition }}`. Copy the service and env layout from the integration job in `tests.yml`.
6. In `Dockerfile`, runtime stage, add `COPY --from=builder /app/evidence evidence/` after the `gateway/` line.
7. Write tests 5.3 and 5.4.

**Allowed files.** `pyproject.toml` (markers only), `tests/conftest.py`, `tests/editions/__init__.py` and `tests/editions/test_edition_smoke.py` (new), `scripts/ci/edition_smoke.sh` (new), `.github/workflows/editions.yml` (new), `Dockerfile`, `tests/unit/test_editions_workflow.py` (new), `tests/unit/test_compose.py`, `build-log.md`.

**Tests.** From `test-spec.md`:
- 5.1 `tests/editions/test_edition_smoke.py::test_edition_smoke`: runs the smoke set for the edition named by `ENABLED_MODULES`.
- 5.2 `scripts/ci/edition_smoke.sh`: with no argument it runs all five editions and exits non-zero if any fails; with one argument it runs that edition only.
- 5.3 `tests/unit/test_editions_workflow.py::test_matrix_calls_the_script_for_each_edition`: `.github/workflows/editions.yml` has a matrix with the five editions, and each job runs `scripts/ci/edition_smoke.sh ${{ matrix.edition }}`.
- 5.4 `tests/unit/test_compose.py::test_runtime_image_copies_evidence`: the `Dockerfile` runtime stage has a `COPY` of `evidence/`.

**Commands.** (live-tier variables exported)
```
scripts/ci/edition_smoke.sh
scripts/ci/edition_smoke.sh Gateway
scripts/ci/edition_smoke.sh Nope; echo "exit $?"
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
~/.local/share/poetry233/bin/poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/ci
```

**Done when.** `edition_smoke.sh` passes all five editions. The `Nope` run exits 2. Tests 5.3 and 5.4 pass. The unit tier and ruff pass. The Architect runs the container proof (5.5).

---

## WP6: UI
**Goal.** The UI checks are green, and module gating has tests. (Finding R12.)

**Read.** `ui/src/app/modules.ts`, `ui/src/app/nav.ts`, `ui/src/app/command-palette.tsx`, `ui/src/features/system/modules-page.tsx`, `ui/src/features/ask/`, `ui/src/features/runs/`, the session provider (`grep -rn "SessionProvider" ui/src`), `ui/e2e/` (existing specs and their setup), `docs/design/` and `.claude/skills/governed-design/SKILL.md` for any visible text.

**Task.**
1. Fix the two TypeScript errors: `src/app/command-palette.tsx(23,11)` (`modules` unused: use it to filter the palette entries, which test 6.3 needs) and `src/app/modules.ts(20,76)` (`enabledModules` possibly undefined: treat undefined as "metadata unknown", so optional items stay hidden).
2. The 22 failing tests in `src/app/command-palette.test.tsx`, `src/features/ask/ask-page.test.tsx`, `src/features/ask/ask-run.test.tsx` and `src/features/runs/runs-page.test.tsx` fail with "useSession must be used inside SessionProvider". Fix only their render harness: wrap the rendered tree in the session provider and supply module metadata (mock `GET /v1/system/modules` the same way each file mocks its other requests). Do not change any `expect(...)` line. List each changed harness under "Changed tests".
3. Write tests 6.1 to 6.7 (Vitest) and 6.8, 6.9 (Playwright).

**Allowed files.** Files under `ui/src/` and `ui/e2e/`, `ui/playwright.config.ts` only to add the Gateway-edition server, `build-log.md`.

**Tests.** From `test-spec.md`, 6.1 to 6.9, with these exact names:
- 6.1 `ui/src/app/nav.test.ts` › `hides items of disabled modules`: nav with metadata where `agents` is off has no `/app/runs`. With `agents` on it has it.
- 6.2 `ui/src/app/nav.test.ts` › `hides optional items while metadata is unknown`: with metadata loading or failed, there is no `/app/runs`. The gateway items are present.
- 6.3 `ui/src/app/command-palette.test.tsx` › `palette hides disabled module entries`: with `agents` off, searching "runs" in the palette gives no Agent runs entry.
- 6.4 `ui/src/app/modules.test.tsx` › `metadata is refetched on session change`: changing the session's principal id gives a new query key, and the old data is not used.
- 6.5 `ui/src/features/ask/ask-page.test.tsx` › `agent mode hidden when agents off`: with `agents` off, the Agent option is absent and Search submits.
- 6.6 `ui/src/features/ask/ask-page.test.tsx` › `stale agent mode sends no agent request`: with Agent selected, metadata changes to `agents` off, then submit. No request goes to `/v1/agent/query`, Search is not called automatically, and the mode is reset for the next manual submit.
- 6.7 `ui/src/features/ask/ask-page.test.tsx` › `retry keeps the original mode`: after an Agent error, retry calls `/v1/agent/query` again with the same question while agents is on. With agents off, retry is blocked and shows the module-unavailable message.
- 6.8 `ui/e2e/modules.spec.ts` › `gateway edition hides agents and keeps search and trust`: against a Gateway-only API (`ENABLED_MODULES=gateway`): the Agent runs link is absent, Platform > Modules lists Agents as off, grouped by pillar, Search returns an answer, Ask has no Agent option, and the Trust receipt verification for a decision passes.
- 6.9 `ui/e2e/modules.spec.ts` › `direct agent runs url shows module unavailable`: opening `/app/runs` directly in the Gateway edition shows the module-unavailable state, and no request to `/v1/agent/runs` is made.

**Commands.** (in `ui/`, with Node 24 on `PATH`)
```
npm run typecheck
npm run lint
npx vitest run
npm run copy-check
npm run tokens:check
```
Do not run Playwright. The Architect runs it.

**Done when.** Typecheck and lint have 0 errors. Vitest: all files pass, including 6.1 to 6.7. `ui/e2e/modules.spec.ts` exists with 6.8 and 6.9. No `expect(...)` line in an existing test changed.

---

## WP6b: Modules page explains itself (runs after WP4)
**Goal.** An admin can tell what each module does and how to change it. (Finding R14.)

**Task.**
1. Regenerate `ui/src/api/schema.d.ts` (`npm run gen:api`) so `ModuleInfo` has `description`.
2. In `ui/src/features/system/modules-page.tsx`, show each module's `description` under its label.
3. When at least one module is off, show one note above the pillars: "Modules are chosen at deploy time with the `ENABLED_MODULES` setting." with a link to the modules section of the deployment docs. Do not add a toggle; the API has no write route.
4. Write test 6.10. Follow `docs/design/` and the governed-design skill for text and layout.

**Allowed files.** `ui/src/api/schema.d.ts`, `ui/src/features/system/modules-page.tsx`, `ui/src/features/system/modules-page.test.tsx` (new), `build-log.md`.

**Tests.**
- 6.10 `ui/src/features/system/modules-page.test.tsx` › `explains each module and how to change it`: each module row shows its description. When at least one module is off, the page shows one note that modules are set by the `ENABLED_MODULES` setting at deploy time, with a link to the deployment docs. No toggle is shown.

**Commands.** As WP6.

**Done when.** Typecheck, lint and Vitest pass, including 6.10.

---

## WP7: Docs
**Goal.** The docs describe modules, editions, ports and deploy shapes. (Finding R8.)

**Task.**
1. Write `docs/adr/0013-module-boundaries.md` from `docs/adr/TEMPLATE.md`: the module registry, editions, the `module` stage, import contracts, the gateway deployment modes (embedded, sidecar, standalone proxy) and the deploy shape. Add it to `docs/adr/README.md`.
2. Add a "Modules and editions" section to `docs/architecture.md`, and a "Modules" section to `docs/deployment.md` (anchor `#modules`) that says how to set `ENABLED_MODULES` and `DEPLOY_SHAPE` for each edition.
3. Update `docs/contracts/ports.md` with `DecisionSink`, `EvidenceLookup`, `DataAccess` and `LineageEmitter`, using the signatures in `architect-disposition.md` ("Port contracts").
4. Write `docs/design/IA.md`: the nav groups, which module owns each, and the hide rules (hidden while metadata is unknown).
5. Add the eight terms to the "Vocabulary" section of `planning/DOMAIN.md`: module, pillar, edition, deploy shape, module stage, record version, extension, evidence core. One plain sentence each.
6. Write `scripts/showcase/README.md`: how to start each edition with `ENABLED_MODULES`.
7. Regenerate `docs/configuration.md` with the command that `tests/unit/test_docs_generated.py` names.
8. `AGENTS.md`: add `evidence` to the ruff line (line 55) and to the mypy package list (line 56). Delete the sentence "Service security rebuilds use pinned inputs and are scanned as final artifacts." from line 16 only if it is not true for this tree; otherwise leave it. Delete any line that says the hosting is Render.

Write in short, plain sentences, as `AGENTS.md` asks.

**Allowed files.** The files named above, `build-log.md`.

**Commands.**
```
~/.local/share/poetry233/bin/poetry run pytest -q -p no:cacheprovider tests/unit/test_docs_generated.py tests/unit/test_docs_links.py
~/.local/share/poetry233/bin/poetry run pytest -m unit -q -p no:cacheprovider
```

**Done when.** Every file above exists or is updated. The two doc tests and the unit tier pass.

---

## WP8: Final evidence
**Goal.** One captured output per acceptance item, then the report.

**Task.**
1. For each item in `acceptance.md`, run the command that proves it and save the output under `evidence/` with the file name the item gives. A1 uses the full unit tier, the live tiers with JUnit, `scripts/check_skips.py`, ruff, mypy, `lint-imports` and the UI checks. State the test counts against Sprint 011 (unit 902, live 835 passed and 10 skips).
2. Write `report.md` in this folder: what was built, the test delta, each acceptance item with its evidence file, and what is open.
3. Update `planning/STATE.md` and add a Sprint 012 entry to `CHANGELOG.md`. The entry has an "Upgrade notes" list with: (a) `DEPLOY_SHAPE` now defaults to `single_tenant`, and a database with more than one tenant must set `DEPLOY_SHAPE=multi_tenant` or the API and workers refuse to start; (b) `ENABLED_MODULES` defaults and what each edition turns off; (c) migration 0011 is required.
4. Leave `evidence/container-gateway.txt` and `evidence/playwright.txt` to the Architect.

**Allowed files.** `planning/sprints/012-pillars-and-boundaries/evidence/*`, `report.md`, `planning/STATE.md`, `CHANGELOG.md`, `build-log.md`.

**Done when.** Every acceptance item except A3's container part and A7 has its evidence file, and `report.md` lists them.
