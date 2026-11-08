# Sprint 012: Test specification

The Architect wrote these tests before the code. Builders write each test with exactly this name, setup and expected result. A builder may add tests. A builder never changes, skips or loosens a test listed here. If a listed test seems wrong, the builder writes it in `build-log.md` under "Spec questions" and leaves that test as specified.

Tiers: **U** is unit (`-m unit`, no services). **I** is integration (`-m integration`, real Postgres and Valkey). **E** is edition smoke (`-m edition_smoke`). **V** is Vitest. **P** is Playwright.

Shared rules:
- A disabled-module answer is HTTP 404 with body `{"error": {"code": "module_disabled", ...}}`.
- "Deny row" means one new `gateway_decisions` row for the tenant with `outcome='deny'`, `stage='module'` and `reason='module_disabled'`.
- Tests that need two tenants use `deploy_shape="multi_tenant"`. The `tenants` fixture already does.

## Baseline (measured 2026-10-28, before WP1)
Sprint 011 accepted numbers: 884 unit passed (902 after round 2b). Integration and e2e: 835 passed and 10 allowed skips.
Measured in this worktree: see `evidence/baseline-2026-10-28.txt`. A1 states the final delta against the 011 numbers.

## Threat-model test names
`threat-model.md` names some tests that exist under other names. They map as follows:
- T2 `test_record_v2.py::test_v1_rows_verify_unchanged` is `tests/unit/test_record_canonical.py::test_legacy_unicode_timezone_and_row_hash_preserve_captured_bytes` and `::test_versions_verify_with_the_same_checks_online_and_offline`.
- T3 `test_float_extension_refused` is `tests/unit/test_record_canonical.py::test_nested_floats_are_refused_before_persistence`; `test_extension_order_does_not_change_hash` is test 1.6; the byte boundary is `::test_size_limit_counts_canonical_utf8_bytes`; mutation is `tests/unit/test_evidence_ports.py::test_decision_entry_takes_a_deep_immutable_copy_of_extensions`.
- T4 `test_failure_raises` is `tests/contracts/test_decision_sink_contract.py::test_sink_write_failure_is_propagated`.

## WP1: Live tiers green
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 1.1 | whole integration and e2e tier | I | `pytest -m "integration or e2e" -rs` passes. The only skips are the 10 on the allowlist (`scripts/check_skips.py`). | A1 |
| 1.2 | `tests/integration/test_migration_record_v2.py::test_upgrade_keeps_v1_chain_and_adds_v2` | I | Given a database at revision 0010 with 3 chained decision rows for one tenant. When it upgrades to 0011. Then the 3 rows have `record_version=1` and `extensions='{}'`; a new decision through `PgDecisionSink` gets `record_version=2`; and chain verification over all 4 rows passes. | A4, T2 |
| 1.3 | `tests/integration/test_migration_record_v2.py::test_v1_row_with_extensions_is_rejected_by_the_database` | I | After the upgrade, an owner-role UPDATE that sets `extensions='{"x":1}'` on a v1 row fails with a check violation. | T2 |
| 1.4 | `tests/integration/test_migration_record_v2.py::test_old_unfiltered_claim_is_not_executable_by_app` | I | At head, `has_function_privilege('gap_app', 'jobs_claim(text, integer)', 'EXECUTE')` is false and the 3-argument version is true. PUBLIC has EXECUTE on neither. | disposition 6 |
| 1.5 | `tests/integration/test_record_v2.py::test_mixed_chain_receipts_verify_offline` | I | One v1 row (inserted at revision 0010, then upgraded) and one v2 row in the same tenant chain. `GET /v1/receipts/{id}` for each, then `scripts/verify/receipt.py` verifies both offline (exit code 0). Changing one character of either receipt's decision makes it exit non-zero. | A4 |
| 1.6 | `tests/unit/test_record_canonical.py::test_extension_order_does_not_change_hash` | U | Two v2 records that are equal except for the insertion order of the same extension keys (schema registered in the test) give the same `compute_row_hash`. | T3 |

## WP2: Composition boundary
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 2.1 | `tests/unit/test_worker_handlers.py::test_gateway_edition_registers_ingest_and_purge_only` | U | `build_handlers` with `ENABLED_MODULES=gateway` returns exactly the keys `{"ingest", "purge_decisions"}`. | R1, A5 |
| 2.2 | `tests/unit/test_worker_handlers.py::test_agents_edition_adds_agent_run` | U | With `gateway,agents` the keys are exactly `{"ingest", "purge_decisions", "agent_run"}`. | A5 |
| 2.3 | `tests/unit/test_worker_handlers.py::test_worker_context_imports_no_agent_code` | U | A fresh `python -c` subprocess that imports `workers.context` and calls `build_handlers` with `ENABLED_MODULES=gateway` (fakes) ends with no `api.agent`, `api.mcp`, `sandbox_agent`, `langgraph` or `openshell` module in `sys.modules`. | A5, T1 |
| 2.4 | `tests/unit/test_gateway_package_api.py::test_agent_and_mcp_import_only_the_gateway_package` | U | An AST scan of `api/agent/**`, `api/mcp/**` and `sandbox_agent/**` finds no `from gateway.<x> import` and no `import gateway.<x>`. Only `from gateway import ...` is allowed. | blueprint import rules |
| 2.5 | `tests/integration/test_module_disabled.py::test_worker_does_not_claim_disabled_job_kinds` | I | Queue one `agent_run` job and one expired-lease `agent_run` job, plus one `ingest` job. Run one worker with `ENABLED_MODULES=gateway` until it is idle. The ingest job reaches `succeeded`. Both agent jobs keep their exact status, attempts and lease. | A5, T1 |

## WP3: Import contracts
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 3.1 | `tests/unit/test_import_contracts.py::test_tree_passes` | U | `lint-imports` on the repo exits 0. | A2, T5 |
| 3.2 | `tests/unit/test_import_contracts.py::test_seeded_violation_fails[from_gateway_policy]` | U | Copy the import-linter config and the needed packages to a temp tree. Add `from gateway.policy import evaluate` to `api/agent/` code. `lint-imports` exits non-zero and names the contract. | A2 |
| 3.3 | `tests/unit/test_import_contracts.py::test_seeded_violation_fails[from_gateway_import_policy]` | U | Same with `from gateway import policy`. Exits non-zero. | A2 |
| 3.4 | `tests/unit/test_import_contracts.py::test_seeded_violation_fails[evidence_imports_gateway]` | U | Same with `import gateway` inside `evidence/`. Exits non-zero. | A2 |
| 3.5 | `tests/unit/test_import_contracts.py::test_ci_lint_job_runs_lint_imports` | U | `.github/workflows/tests.yml`, lint job, has a step that runs `poetry run lint-imports`. | A2 |

## WP4: API contract and authority
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 4.1 | `tests/unit/test_action_module_map.py::test_every_action_kind_maps_to_module` | U | Every `ActionKind` member is a key in `ACTION_MODULES`, and each value is in `MODULE_NAMES`. | A5 |
| 4.2 | `tests/unit/test_action_module_map.py::test_modules_have_pillars` | U | Every `ModuleSpec.pillar` is in `{"platform", "gateway", "data", "agents"}`. | A8 |
| 4.3 | `tests/integration/test_system_modules.py::test_each_single_scope_key_reads_metadata[<scope>]` | I | For each scope in `kb:read`, `kb:write`, `query`, `agent`, `audit:read` and `admin`, a key with only that scope gets 200 from `GET /v1/system/modules`. The body has `deploy_shape`, `edition`, and `modules`, where every item has `name`, `label`, `pillar`, `enabled`, `nav_group` and `always_on`. | A8 |
| 4.4 | `tests/unit/test_system_read_scope.py::test_metadata_scope_grants_no_other_action[<scope>]` | U | For each scope, `build_boundary(principal_with_only_that_scope, None).actions` equals the pre-012 set for that scope plus only `"system.read"`. The test writes the pre-012 sets as literals, copied from `SCOPE_ACTIONS` at commit `555ca5f` (`git show 555ca5f:gateway/boundary.py`). | A8 |
| 4.5 | `tests/integration/test_system_modules.py::test_no_credential_is_401_and_unknown_scope_is_403` | I | No header gives 401. A key whose stored scopes are empty gives 403. | A8 |
| 4.6 | `tests/integration/test_module_disabled.py::test_every_route_of_a_disabled_module_is_denied` | I | App with `ENABLED_MODULES=gateway`. For each entry of `DISABLED_AGENT_ROUTES`, an authenticated call with the right scope answers 404 `module_disabled`, and exactly one deny row is added. | A5, T1, T6 |
| 4.7 | `tests/integration/test_module_disabled.py::test_deny_is_recorded` | I | `POST /v1/agent/query` with an `agent` key under `ENABLED_MODULES=gateway` gives 404 `module_disabled` and a deny row with `action='agent.run'`. | A5, T6 |
| 4.8 | `tests/integration/test_module_disabled.py::test_missing_credential_or_scope_wins_over_module` | I | Under `ENABLED_MODULES=gateway`: no credential on `POST /v1/agent/query` gives 401; a `query`-only key gives 403; neither adds a deny row with reason `module_disabled`. | A5 |
| 4.9 | `tests/unit/test_openapi_snapshot.py` (existing) | U | The refreshed snapshot has `ModuleList`, and `DecisionDetail` and `Receipt.decision` have `record_version` (integer) and `extensions` (object). | R3, R4 |
| 4.10 | `tests/integration/test_record_v2.py::test_api_shows_version_and_extensions` | I | `GET /v1/decisions/{id}` for a new decision returns `record_version: 2` and `extensions: {}`. For a v1 row it returns `record_version: 1` and `extensions: {}`. | A4 |
| 4.11 | `tests/integration/test_deploy_shape.py::test_single_tenant_startup_refuses_two_tenants` | I | Database with two tenants. Starting the app lifespan with `DEPLOY_SHAPE=single_tenant` raises `RuntimeError` that names `DEPLOY_SHAPE`. With `multi_tenant` it starts. | A9 |
| 4.12 | `tests/integration/test_deploy_shape.py::test_concurrent_second_tenant_creation_is_refused` | I | Database with one tenant. Two threads call `create_tenant(..., deploy_shape="single_tenant")` at the same time for two new slugs. Both fail with `AdminError`, and the tenant count stays 1. On an empty database, two concurrent creates give exactly one success. | A9, T7 |
| 4.13 | `tests/integration/test_deploy_shape.py::test_probe_grants_and_search_path` | I | `deploy_shape_has_multiple_tenants()`: PUBLIC has no EXECUTE, `gap_app` has EXECUTE, `proconfig` sets a `search_path` that ends with `pg_temp`, and it returns a boolean. A `gap_app` session that creates `pg_temp.tenants` with 5 rows still gets the true answer. | A9, T7 |
| 4.14 | `tests/integration/test_deploy_shape.py::test_rls_present_in_both_shapes` | I | With each shape, tenant A's key cannot read tenant B's documents or decisions (404 or an empty list, as the existing RLS tests expect). | A9, T7 |
| 4.15 | `tests/unit/test_action_module_map.py::test_modules_have_descriptions` | U | Every `ModuleSpec` has a non-empty `description` of at most 140 characters, and `GET /v1/system/modules` items carry it (`ModuleInfo.description`). | A8, R14 |

## WP5: Editions and the container
Smoke set per edition: boot `create_app` with the real lifespan and fakes, with `ENABLED_MODULES` set to the edition's modules. Then check:
- `GET /v1/health` gives 200.
- `GET /v1/system/modules` gives the edition name, and `enabled` is true exactly for the edition's modules.
- `GET /v1/documents?namespace=default` with a `kb:read` key gives 200 and writes an allow row with `record_version=2`.
- `POST /v1/agent/query` with an `agent` key gives 404 `module_disabled` when `agents` is off. When it is on, it gives 200 or 202 with the fake model.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 5.1 | `tests/editions/test_edition_smoke.py::test_edition_smoke` | E | Runs the smoke set for the edition named by `ENABLED_MODULES`. | A3 |
| 5.2 | `scripts/ci/edition_smoke.sh` | E | With no argument it runs `Gateway`, `Assurance`, `Agents`, `Data` and `Full` and exits non-zero if any fails. With one argument it runs that edition only. | A3 |
| 5.3 | `tests/unit/test_editions_workflow.py::test_matrix_calls_the_script_for_each_edition` | U | `.github/workflows/editions.yml` has a matrix with the five editions, and each job runs `scripts/ci/edition_smoke.sh ${{ matrix.edition }}`. | A3 |
| 5.4 | `tests/unit/test_compose.py::test_runtime_image_copies_evidence` | U | The `Dockerfile` runtime stage has a `COPY` of `evidence/`. | A3, R9 |
| 5.5 | container proof (Architect) | live | Build the app image. Run it with `ENABLED_MODULES=gateway` against the stack. Health is 200, an allowed call writes a decision row, and `POST /v1/agent/query` gives 404 `module_disabled`. Output goes to `evidence/container-gateway.txt`. | A3 |

## WP6: UI
| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 6.1 | `ui/src/app/nav.test.ts::hides items of disabled modules` | V | Nav with metadata where `agents` is off has no `/app/runs`. With `agents` on it has it. | A7 |
| 6.2 | `ui/src/app/nav.test.ts::hides optional items while metadata is unknown` | V | With metadata loading or failed, there is no `/app/runs`. The gateway items are present. | A7 |
| 6.3 | `ui/src/app/command-palette.test.tsx::palette hides disabled module entries` | V | With `agents` off, searching "runs" in the palette gives no Agent runs entry. | A8 |
| 6.4 | `ui/src/app/modules.test.tsx::metadata is refetched on session change` | V | Changing the session's principal id gives a new query key, and the old data is not used. | A8 |
| 6.5 | `ui/src/features/ask/ask-page.test.tsx::agent mode hidden when agents off` | V | With `agents` off, the Agent option is absent and Search submits. | A7 |
| 6.6 | `ui/src/features/ask/ask-page.test.tsx::stale agent mode sends no agent request` | V | With Agent selected, metadata changes to `agents` off, then submit. No request goes to `/v1/agent/query`, Search is not called automatically, and the mode is reset for the next manual submit. | A7 |
| 6.7 | `ui/src/features/ask/ask-page.test.tsx::retry keeps the original mode` | V | After an Agent error, retry calls `/v1/agent/query` again with the same question while agents is on. With agents off, retry is blocked and shows the module-unavailable message. | A7 |
| 6.8 | `ui/e2e/modules.spec.ts::gateway edition hides agents and keeps search and trust` | P | Against a Gateway-only API (`ENABLED_MODULES=gateway`): the Agent runs link is absent, Platform > Modules lists Agents as off, grouped by pillar, Search returns an answer, Ask has no Agent option, and the Trust receipt verification for a decision passes. | A7, A8 |
| 6.9 | `ui/e2e/modules.spec.ts::direct agent runs url shows module unavailable` | P | Opening `/app/runs` directly in the Gateway edition shows the module-unavailable state, and no request to `/v1/agent/runs` is made. | A7 |
| 6.10 | `ui/src/features/system/modules-page.test.tsx::explains each module and how to change it` | V | Each module row shows its description. When at least one module is off, the page shows one note: modules are set by the `ENABLED_MODULES` setting at deploy time, with a link to the deployment docs. No toggle is shown (the API has no write route). | A8, R14 |

## WP7: Docs (checked by existing doc tests and review)
- `docs/adr/0013-module-boundaries.md` exists and is linked from the ADR index.
- `docs/design/IA.md`, `docs/contracts/ports.md`, the `docs/architecture.md` modules section, the eight terms in `planning/DOMAIN.md`, and `scripts/showcase/README.md`.
- `docs/configuration.md` is regenerated, and `tests/unit/test_docs_generated.py` passes.
- `AGENTS.md`: the ruff line and the mypy list include `evidence`. Remove the stale "Hosting: Render" and "Service security rebuilds" lines.

## WP8: Final evidence (builder drafts, Architect verifies)
One captured command output per acceptance item, in `evidence/` with the names in `acceptance.md`. Then `report.md`, `planning/STATE.md` and `CHANGELOG.md`.
