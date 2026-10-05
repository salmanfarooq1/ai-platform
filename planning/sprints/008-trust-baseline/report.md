# Sprint 008: Report

Built and tested in this container, except what is marked "not verified here". Nothing was committed or pushed. Evidence is captured command output in `evidence/`.

## 1. Acceptance

| Check | Status | Evidence |
|---|---|---|
| **A1** all checks pass | **Done, with the standing MinIO skips.** ruff, mypy (136 files), DDL guard clean. Full suite 1294 passed (after the QA fixes; see section 8), 0 failed, 10 skipped (the live-MinIO runs; `check_skips.py --expect 10` passes, no new skip). Frontend: tokens, lint, tsc, copy-check, build, 192 Vitest, 77 Playwright | `backend-ruff.txt`, `backend-mypy.txt`, `backend-ddl.txt`, `backend-pytest.txt`, `backend-skips.txt`, `frontend-*.txt` |
| **A2** receipts | **Done.** A valid receipt verifies offline (the script as its own process, exit 0). A tampered decision, signature, chain link, row hash, position and key each fail, in the script and in the server's verify route with the same failing checks. 40 concurrent decision writes of one tenant give positions 1..N with no gap; an edit, a cut link, a rewritten hash and a removed row are all seen. Foreign and missing give an identical 404. A failed chain step fails an allow closed (503 `decision_unrecorded`) and a deny keeps its row. No input text in the chain, a receipt or a column | `receipts.txt` (50 tests with settings) |
| **A3** retention | **Done.** The purge removes only the expired rows of the right tenant (another tenant with expired rows but a longer retention is untouched), per-tenant override, batches with one checkpoint each, unchained rows by age, everything-expired then a new write continues the chain, checkpoint plus outbox event in one transaction (a failing publish rolls back both), the function refuses another or no tenant and fewer than one day, the app role has no DELETE or UPDATE, scheduler queues one job a day per due tenant, chain verifies across the checkpoint and fails without it, migration `0009` with a non-superuser owner | `retention.txt` (23 tests) |
| **A4** eval gate | **Done.** The suite (12 questions, fake LLM) scores 0.8333 on each metric, equal to `baseline.json`. Mutations that make the fake model answer wrongly, break retrieval, or lower a score by more than the 0.02 tolerance make the gate fail and name the metric. Exact boundary, missing metric, raised baseline, bad baseline file, CLI as CI runs it, CI has the gate step and never runs `run_real.py` | `eval-gate.txt` (12 tests) |
| **A5** cost breaker | **Done.** Priced fake model fills the counter (micro-dollars), the next call is 429 `cost_cap_exceeded` with a chained deny row (stage `cost`), the model is not called. Per day, per tenant, a policy can lower the cap and never raise it. Redis down (only the cost read failing) gives 503 `dependency_unavailable` with a deny row, and the unit test checks the stage alone | `cost-cap.txt` (14 tests) |
| **A6** metrics | **Done, and verified live.** `/metrics` exposes the five series with route templates and no ids. Open in local, `admin` only when `METRICS_PUBLIC=false` (401, 403, 200). Worker serves its own series. `docker compose --profile observability config` is valid. Prometheus and Grafana images pulled here, so `scripts/verify/observability.sh` ran: Prometheus sees the api target up and holds `http_requests_total`, Grafana serves the provisioned dashboard and data source | `metrics.txt` (8 tests and compose config), `observability-live.txt` |
| **A7** Playwright and axe | **Done.** Trust: verify a receipt (valid), then a tampered pasted one (invalid), the decision panel link runs the check on arrival, retention and the recorded eval run show, axe 0 violations in light and dark | `playwright.txt` (77 passed) |

## 2. Test numbers
- Backend: **1294 passed, 0 failed, 10 skipped** (1278 before the QA fixes) (baseline 1188 and 10). New: receipts e2e 25, retention 13, migration 0009 3, trust summary 7, cost e2e 6, cost unit 8, metrics e2e 5, observability profile 3, eval gate 12, settings +4 (counted in the totals).
- Frontend: **192 Vitest** (182 before; 190 before the QA fixes), **77 Playwright** (72 before, +5 in `trust.spec.ts`).

## 3. Existing tests that had to change (none weakened, skipped or deleted)
- Hosted modes require `RECEIPT_SIGNING_KEY`: `test_settings`, `test_config_mode`, `test_web_edge_unit` now set a well-formed key (new tests cover the rule).
- The stage list gained `cost`: `test_the_stage_list_is_in_the_documented_order`.
- `/metrics` is the one more unversioned route: `test_openapi_snapshot`, `test_openapi_lists_only_versioned_product_routes` and `test_every_other_v1_operation_requires_authentication` name it explicitly (its closed mode is tested in `test_metrics.py`).
- Migration head `0009` and its tables: `test_migrations`. `truncate_tables` and the Redis prefixes list the new tables and `cost:`.
- Code fix, not an expectation: the route-tenant-inputs test forbids a `tenant_id` parameter in routers, so the shared helper takes `owner_id`.

## 4. Deviations and decisions
- Receipt for an unchained row (before `0009`, or a deny whose chain step failed) is 409 `receipt_unavailable`; a stored row that no longer matches its hash is 409 `chain_mismatch`. The blueprint only names 404.
- Trust summary adds `eval_history`, `retention_is_default` and `grafana_url`. A `chain_heads` table holds the per-tenant head (blueprint: "a per-tenant chain head").
- The trace id is not in the hashed record (the decision detail does not carry it).
- Decision timestamps are taken from the database clock after the tenant lock, so time never goes backwards along the chain.
- Purge jobs are hidden from `/v1/jobs` (not a caller's job). The scheduler is off in tests (`RETENTION_SCHEDULE_INTERVAL_SECONDS=0`).
- `DAILY_COST_CAP_USD` default 10 and 90 days of retention are placeholders (Q26). Cost is booked in the FinOps middleware and `book_agent_usage`, once per execution id.
- `/metrics` is unversioned. Decision counts are per process, so the worker serves its own (`WORKER_METRICS_PORT`, off by default).
- Dependencies: added `opentelemetry-exporter-prometheus`; `deepeval` is now in the `dev` group too (lock regenerated; the existing yanked-version warning for deepeval 4.0.8 remains).
- Landing copy: capability 3 mentions a record can be signed and checked offline, capability 6 mentions the cost cap. The copy-check must-not list no longer holds signed receipts, hash chains, eval gate and dashboards.

## 5. Open questions
Q26 to Q30 in `planning/QUESTIONS.md`: placeholder numbers, retention of the other tables (Q27), receipts for old rows, anchoring the chain outside Postgres, blueprint additions.

## 6. Not verified here
CI on GitHub (including the new `eval-gate` job), the hosted Neon migration (`0009` was tested with a non-superuser owner locally), a real-provider eval run (`run_real.py` was only checked to refuse without `REAL_EVAL=1`), a Docker image build, the compose `worker` service with `WORKER_METRICS_PORT` (the Prometheus worker target was not up in the live check), live MinIO, a human visual review of the Trust page.

## 7. Proposed commits (a human runs them)
```bash
git add migrations/versions/0009_trust_baseline.py core gateway ports adapters workers api config.py docker docker-compose.yml pyproject.toml poetry.lock .env.example
git commit -m "feat: decision hash chain, signed receipts, retention, cost cap and metrics"
git add tests scripts .github
git commit -m "test: receipts, retention, eval gate, cost cap, metrics; eval gate and live observability scripts"
git add ui
git commit -m "feat(ui): Trust page with receipt verification, retention and eval gate"
git add docs README.md AGENTS.md CHANGELOG.md planning
git commit -m "docs: ADR-0012, ARCHITECTURE, content rules, Sprint 008 report"
```

## 8. QA fixes
Findings from `qa-review.md`, applied as the Architect disposition says. Migration `0009` was changed in place (not released). Each fix has a test that fails without it: every one was checked by reverting the fix and running its test, except L5.

| Finding | Fix | Test |
|---|---|---|
| M1 unsigned checkpoints | `gap_app` lost INSERT on `chain_checkpoints`. Only `decisions_purge_batch` writes a checkpoint. The worker asks `decisions_purge_plan`, signs (tenant, position, row_hash, reason) with the receipt key, and the function recomputes the plan and refuses a checkpoint that is unsigned or is not the computed one. Genesis is derived and needs no row. `verify_checkpoints` and `scripts/verify/receipt.py chain --keys` reject an unsigned or badly signed checkpoint | `tests/integration/test_retention.py::test_m1_the_app_role_cannot_write_a_checkpoint`, `::test_m1_the_purge_function_refuses_a_checkpoint_that_is_not_what_it_computes_or_is_unsigned`, `::test_m1_a_purge_checkpoint_is_signed_and_verification_rejects_an_unsigned_or_badly_signed_one`; grants in `tests/integration/test_migration_0009.py` |
| M2 caller sets retention | Hard floor of 30 days in the plan and batch functions and in `retention_due_tenants`, whatever the caller passes. `tenants.retention_days` CHECK is at least 30, the CLI refuses less, `DECISION_RETENTION_DAYS` is at least 30. In DECISIONS | `tests/integration/test_retention.py::test_m2_the_purge_never_goes_below_30_days_whatever_the_caller_passes`; CLI bad values in `tests/e2e/test_trust_summary.py::test_the_admin_cli_sets_and_clears_a_tenants_retention` |
| M3 unpriced model costs 0 | `core/pricing.rates_for`: an unpriced model costs the highest known rate (FinOps, agent usage and the LLM adapter use it). Hosted modes fail at startup (API and worker) when a configured chat, embedding or fallback model has no price. Two embedding prices were added to `MODEL_PRICING` (Q32). The overshoot by concurrent calls is in ADR-0012 and ARCHITECTURE | `tests/unit/test_pricing_and_labels.py::test_m3_*` (3 tests), `tests/e2e/test_cost_cap.py::test_m3_a_model_with_no_price_still_trips_the_cap` |
| M4 method label | Methods outside GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS are labelled `OTHER` | `tests/unit/test_pricing_and_labels.py::test_m4_methods_outside_the_standard_set_share_one_label`, `tests/e2e/test_metrics.py::test_m4_an_invented_http_method_is_one_label_not_a_new_series` |
| L2 plain str key | `receipt_signing_key` is a `SecretStr`, read only through `Settings.signing_key_text` | `tests/unit/test_pricing_and_labels.py::test_l2_the_signing_key_is_a_secret_and_is_not_printed` |
| L5 unsigned fields shown as verified | The Trust page lists under "Verified" only values read from the signed text (and none for an invalid receipt). Principal name, tenant label and the decision link are under "Context, not signed" | `ui/src/features/trust/trust.test.tsx` "L5: only the signed text is shown under Verified..." and "L5: an invalid receipt has no Verified list" |

Accepted and written into ADR-0012 ("Accepted risks"): L1, L3 (Q31), L4, L6.

Existing expectations that changed on purpose: `test_finops.py` and `test_llm.py` (an unknown model no longer costs 0), `test_migration_0009.py` (checkpoint grants, the batch signature), `test_retention.py` (the "at least one day" refusal became the 30-day floor), `test_trust_summary.py` (retention 30 is the lowest value).

Revert check: done for M1 (the grant, and the plan comparison), M2, M3, M4 and L2. Each test failed with the fix removed and passed with it back. Not done for L5.

Numbers after the QA fixes: ruff (including `scripts/eval`), mypy (137 files) and the DDL guard are clean. Backend 1294 passed, 10 skipped, `check_skips.py --expect 10` passes. Frontend: 192 Vitest, build and checks pass, Playwright 77 passed. New open questions: Q31 (key revocation) and Q32 (embedding prices).
