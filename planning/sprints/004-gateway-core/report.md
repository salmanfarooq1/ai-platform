# Sprint 004: Gateway core. Report

The Builder returned this as text, and the Architect saved it in condensed form. The full requirement-to-test and scenario-to-test tables are in `build-log.md` and in the test file names below.

## 1. Acceptance
| Check | State | Evidence |
|---|---|---|
| A1 ruff, mypy, ddl, unit | done | `ruff.txt`, `mypy.txt` (81 files), `pytest-unit.txt` (424) |
| A2 int+e2e | done | `pytest-int-e2e.txt` (284, 0 skipped; 285 after QA fix N1). The Sprint 003 rate and budget tests are byte-for-byte unchanged |
| A3 req and scenario → tests | done | `tests/unit/test_gateway_{enforce,boundary,policy,import_lint,packaging}.py`, `tests/integration/test_gateway*.py`, `tests/e2e/test_gateway_e2e.py`, `tests/e2e/test_gateway_followups.py` (`test_1_…` to `test_9b_…` map to scenarios 1–9) |
| A4 middleware removed, import-lint | done | `grep-middleware.txt` |
| A5 live two-tenant run | done | `live-curl.txt`, `decisions-psql.txt`, `redis-down-live.txt` (0 query-text hits in the pg_dump) |
| A6 fail-closed parametrized over stages | done | `test_an_exception_in_any_stage_is_a_deny_internal_error[…]` |
| A7 property tests ≥200 | done | `hypothesis-stats.txt` (3 × 300) |
| A8 0005 on data | done | `migrate.txt` (md5 digests identical) |
| A9 ADR-0006, docs, OpenAPI | done | |

## 3. Tests
Before: 492. After: **709 passed, 0 failed, 0 skipped** (unit 424, int+e2e 285, including the QA fix N1). Mutation check: making `enforce()` allow on a stage exception failed 8 tests, and making the rate check fail open failed 2. After the QA follow-ups: letting a failed decision write stay an allow failed 4 tests, and removing the halt check in the verifier failed 2 (`mutation.txt`). The Architect re-ran the suite.

## 4. Existing tests changed (no assertion loosened)
- `test_middleware_paths.py`: imports only.
- `test_agent_tools.py`: tools now take the gateway context.
- `test_mcp_tools.py::test_search_documents_blocked_query`: binds a principal.
- `test_tenancy.py`: `agent_config` helper.
- `test_migrations.py`: head is 0005.
- `harness.py`: truncates the new tables.
- `api/agent/graph.py` imported `asyncpg.Pool`, which the import guard bans. It now uses `DbPool`.
- Bug found: the Dockerfile runtime stage didn't copy `gateway/`. Fixed, with a test.

## 5. Skipped
- Image build (sandbox), B11.
- The live run used the LLM fakes (no keys).
- Out of scope: OPA, PII, approvals, A2A, decision retention (Q7).

## 6. Decisions
- **Default policy (no row):** every KB, tool and model, `max_tool_calls` 50, 100k tokens. Scopes still decide action kinds, and a policy can only narrow. ADR-0006.
- **Redis down:** 503 `dependency_unavailable`. Fail closed, and QA M2 is closed. Token booking after the work stays best effort.
- **Deny mapping:** 403 `policy_denied (reason: …)`. Guardrails stay 400 `query_blocked`. Limits give 429, dependencies give 503.
- **Order:** guardrails run before the rate limit. Gateway checks run before `require_kb`.
- **Tool calls:** verifier retries share `max_tool_calls`. A deny ends the loop with a partial answer, `flagged=true` and `flag_reason`.
- **Decision record:** one row per `enforce()` call. A failed write on an allow gives 503 `decision_unrecorded`. Token booking after the work stays best effort. `input_hash` is SHA-256 only.
- **Policies:** append-only (trigger), one active version per tenant (partial unique index). The app role has SELECT only.
- **Deferred:** one insert per governed call, one policy read per request, `gateway/guardrails.py` imports a private helper, the agent's low-confidence flag isn't applied.

## 8. Hosted
Deploy runs 0005. No policy rows means the default, so behaviour stays as today (Q8).

## QA follow-ups closed
- **M1:** MCP gates `tool.call` and `model.invoke`. `test_m1_…` in `test_gateway_followups.py`.
- **M2:** a failed decision write on an allow gives 503 `decision_unrecorded`. Unit, integration and e2e tests revoke INSERT from `gap_app`. The Architect re-ran the e2e attack.
- **M3:** `/v1/config` lists only allowed KBs.
- **M4:** new actions `feedback.write` and `analytics.read`. The scope map gives `tool.call` to `kb:read` and `query`, and `model.invoke` to `kb:write`.
- **L1:** `api/agent/models.py` is the only module that imports a provider. An AST check (`tests/gate_lint.py`, `test_gateway_gate_calls.py`) proves every agent tool, MCP tool and MCP resource calls the gate. `graph.py` is in the import guard.
- **L2:** scope denials write a deny row. A missing `query` scope on `/v1/feedback` is recorded as `kb.read`.
- **L3:** completion tokens count against `max_tokens_per_request`.
- **L4:** no verifier call after a halt.
- **L7:** 403 for unknown KBs under a KB allowlist. Accepted, noted in ADR-0006.
- **L5, L6:** accepted. **L8:** handled by the commit plan.
- Policies can't deny `feedback.write` or `analytics.read` by resource. The deny test uses a broken policy row.
