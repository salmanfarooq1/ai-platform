# Sprint 009: Report

Built and tested in this container. Nothing was committed or pushed. Evidence is captured command output in `evidence/`. The live OpenShell run is marked with what it was and was not (section 6).

## 1. Acceptance

| Check | Status | Evidence |
|---|---|---|
| **A1** all checks pass, the adapter passes the AgentRuntime contract | **Done, with the standing 10 MinIO skips.** (The acceptance text says "0 skipped"; the baseline has 10 live-MinIO skips and the brief says to keep exactly that, so `check_skips.py --expect 10` passes and no skip was added.) The OpenShell runtime passes the AgentRuntime contract suite (12 parametrised tests, the same suite the other two runtimes pass) **against the fake sandbox, not a real one**: `tests/fake_sandbox.py` enforces the same policy but is not a recording. The `SandboxDriver` port has its own contract suite (18 tests: the fake and the SDK driver with SDK stand-ins). ruff, mypy (146 files) and the DDL guard are clean. | `backend-pytest.txt`, `backend-skips.txt`, `backend-ruff.txt`, `backend-mypy.txt`, `backend-ddl.txt` |
| **A2** the agent completes an authorised task in the sandbox | **Done, tested on the fake and run live.** Fake: the real `sandbox_agent/entry.py` runs under the fake sandbox against the real app, worker, Postgres and Redis (retrieve, model call, stored answer, every decision carries the `execution_id`, usage booked once by the gateway). Live: against OpenShell 0.1.2, one allowed `tool.call`, events `start` and `exit`, not flagged. | `backend-pytest.txt` (`tests/e2e/test_sandbox_runs.py`), `openshell-live.txt` |
| **A3** a direct call to a model provider fails and a network-deny event is recorded | **Done, tested on the fake and run live.** Live: the call failed (`URLError`) and OpenShell itself wrote `NET:OPEN [MED] DENIED ... -> api.openai.com:443 [reason:transparent_tcp_policy_denied]`, which became a `network_denied` row. The only route the policy allows is the gateway (the fake test tries four other targets). | `openshell-live.txt`, `backend-pytest.txt` |
| **A4** reading a file outside the work directory fails and an event is recorded | **Done, with one honest limit.** The read fails live with `PermissionError` (Landlock). **OpenShell 0.1.2 logs no event for a refused read**, so the `file_denied` row for the check run comes from the probe's own report and is marked `source: agent_check`. A real agent run that tries a forbidden read leaves no event (Q37, risk S9-3). The probe file is `/var/lib/dpkg/status`, because OpenShell adds `/etc` to the readable baseline: the first probe, `/etc/hostname`, was readable. | `openshell-live.txt`, `backend-pytest.txt` |
| **A5** an unauthorised tool argument gets a deny row `tool_argument_not_allowed` | **Done.** Real Postgres and the real `enforce()`: a deny row with the reason, stage `policy`, the run's `execution_id`, on the hash chain, with no argument value stored anywhere in the row. Through the sandbox path the run ends partial and flagged and the model is never asked. Live too. The check also covers LangGraph and MCP tools. | `backend-pytest.txt`, `openshell-live.txt` |
| **A6** sandbox events join `gateway_decisions` by `execution_id` in the runs API and on the Agent runs page (Playwright) | **Done.** `GET /v1/agent/runs/{execution_id}` returns `sandbox_events` and a `timeline` of decisions and events merged by time (another tenant or another principal: 404). The page shows them with one icon and one word per kind; a blocked network call or file access is a deny state. Playwright: a run where the sandbox blocked both, a clean run, and axe in both themes (0 serious or critical). **The Playwright runs were made while seeding, with the fake sandbox**, so they prove the page and the API, not OpenShell. | `playwright.txt`, `frontend-vitest.txt`, `backend-pytest.txt` |
| **A7** A2 to A5 run live via `scripts/verify/openshell.sh`, or "not verified here" with the runbook | **Done live, on one setup** (section 6): OpenShell 0.1.2, Docker driver, a gateway from the checksum-checked Debian package, locally rebuilt runtime images, a local workload image. All of A2 to A5 and three more checks (memory limit kills a hog, CPU and memory limits on the container, cancel removes the sandbox) passed. The runbook is `docs/runbooks/openshell.md`. | `openshell-live.txt`, `openshell-sdk-surface.txt` |

## 2. Test numbers
- Backend: **1504 passed, 0 failed, 10 skipped** (baseline 1294 passed, 10 skipped; +210). The 10 skips are the live-MinIO runs of Sprint 006 (`check_skips.py --expect 10` passes). New tests: 193 in nine new files (tool arguments 25, sandbox units 58, SDK driver 11, migration `0010` 8, run tokens 13, tool argument deny rows 7, OpenShell runtime 28, end to end 25, `SandboxDriver` contract 18), 12 more in the AgentRuntime contract (the new runtime), 4 import-lint cases, and the rest are existing parametrised tests that gained a case.
- Frontend: **207 Vitest** (192 before, +15: `RunSteps`, the sandbox words and four runs-page cases), **82 Playwright** (77 before, +5 in `sandbox.spec.ts`).
- Live: `scripts/verify/openshell.sh` 25 SDK-surface checks and 13 live checks, all passed. `scripts/verify/openshell_sdk_surface.py` runs without a gateway.
- Revert checks: seven guards were removed one at a time and the tests that guard them failed each time (`revert-checks.txt`).

## 3. Existing tests that had to change (none weakened, skipped or deleted)
- Migration head `0010` and the two new tables: `test_migrations` (head, table set) and `truncate_tables` in `tests/harness.py`.
- The import lint now bans `openshell` outside `adapters/` (`SDK_ONLY_IN_ADAPTERS`), and "the adapters really hold the SDKs" names the new driver.
- The AgentRuntime contract suite gained a third runtime (`openshell`), and the failed-run error expectation now has a third case: the in-process runtime keeps the text, the queued runtime stores `agent_run_failed`, the OpenShell runtime stores `sandbox_exit_1`.
- `test_gateway_packaging`: the Dockerfile copies `sandbox_agent` (the runtime hands its source to a sandbox, so the default image needs the file), CI lints `sandbox_agent`, and mypy covers it.
- Code fix, not an expectation: `test_in_routers_every_use_of_tenant_id_derives_from_the_principal` rejected `ctx.principal.tenant_id` in the new router; the router now uses `principal.tenant_id`.
- Type fix only: the Vitest mocks of `agentRun` kept their type because the page uses a new `agentRunDetail` call.

## 4. Deviations and decisions
- **The default runtime stays `queued`**, not "in-process" as the requirements text says: Sprint 007 changed the default (Q36).
- **`AGENT_RUNTIME=openshell` selects the sandbox in the worker.** The API still builds the queued runtime, so job status, the runs API and the sync wait are unchanged. The blueprint says the adapter is "selected by `AGENT_RUNTIME=openshell`"; this is how.
- **The agent in the sandbox is a thin retrieve-then-answer program** (`sandbox_agent/entry.py`, standard library only), not the LangGraph agent (Q34).
- **The fake is a test double, not a recorded fake.** The brief called for a recorded fake when OpenShell cannot run. OpenShell could run here, so the real driver exists and was run; the fake is for the unit, contract and e2e tiers and says it is not a recording.
- **Facts came from reading, not from the documentation site** (blocked). The docs at tag `v0.1.2`, the installer, the checksums and the wheel were readable and are the sources (runbook table).
- **File-denied and limit events are partly derived** (see A4): `source` says where a row came from. Exit 137 becomes a `limit_hit` row with `source: exit_code`.
- **`jsonschema` is now a direct dependency** (it was already in the lock file through other packages). The lock file changed only in its content hash.
- **`principals` gained a unique `(id, tenant_id)`** so `run_tokens` can have a composite foreign key: a plain foreign key ignores row-level security and let a test point a token at another tenant's principal.
- **The cost in a sandboxed answer is what the agent reported;** booked usage is measured at the gateway (Q40).
- Blueprint additions to confirm are in Q39.

## 5. Open questions
Q33 to Q40 and B14 in `planning/QUESTIONS.md`: who owns the OpenShell pin (Q33), the thin agent (Q34), retention of the two new tables (Q35), the default runtime (Q36), file-deny events (Q37), hosting a sandbox worker (Q38), blueprint additions (Q39), the answer's cost (Q40), and the locally built images (B14). New risks S9-1 to S9-8 are in `planning/RISKS.md`.

## 6. Not verified here
- **The standard OpenShell images** (`ghcr.io/nvidia/openshell/supervisor` and `sandbox`, tag 0.1.2). The container could not pull them (the blob host was forbidden), so the live run used images rebuilt from the checksum-checked release archives. The default workload image (`nvcr.io`) was also unreachable; a local Ubuntu 22.04 image with Python 3.10 was used.
- **Anything other than the Docker driver, OpenShell 0.1.2 and this kernel** (Linux 6.18, Landlock ABI 7): Podman, Kubernetes, the microVM driver, WSL 2, macOS, older kernels (the reduced legacy mode), other OpenShell versions.
- **A real model.** The live run used the fake model and embeddings, so it checks the sandbox and the gateway path, not an LLM.
- The wall-clock limit against a real sandbox (it is tested with the fake, and cancelling a live run was checked), more than one run at a time, and the gateway restarting mid-run.
- CI on GitHub (the new lint scope and the migration), a Docker image build (the Dockerfile change was checked by a test that reads it), and the hosted Neon migration `0010`.

**Left in this container (outside the repository):** the locally built Docker images `ghcr.io/nvidia/openshell/supervisor:0.1.2`, `ghcr.io/nvidia/openshell/sandbox:0.1.2` (rebuilt from release archives, not the project's images) and `local/openshell-workload:py`; the extracted package and gateway state under `/tmp/os9`. The gateway process was stopped.

## 7. Proposed commits (a human runs them, after the blocks for Sprints 005 to 008 in `planning/COMMIT_PLAN.md`)
```bash
git add migrations/versions/0010_sandbox_events_run_tokens.py ports adapters gateway core api workers sandbox_agent Dockerfile pyproject.toml poetry.lock .env.example
git commit -m "feat: sandboxed agent runs on OpenShell, run tokens, tool argument checks and sandbox events"
git add tests scripts .github
git commit -m "test: sandbox runtime, run tokens, tool arguments and the runs API; live OpenShell verify script"
git add ui
git commit -m "feat(ui): sandbox events on the Agent runs step timeline"
git add docs README.md AGENTS.md CHANGELOG.md planning
git commit -m "docs: ADR-0009 OpenShell section, runbook, ARCHITECTURE, Sprint 009 report"
```

## 9. QA fixes
Applied from `qa-review.md` as the Architect disposition says. Migration `0010` was changed in place (`run_tokens.key_id` and the lookup function). The driver and sandbox policy were not touched, so the live script was not re-run. Each fix has a test that fails without it; each was checked by removing the fix and running the test (all failed).

| Finding | Fix | Test |
|---|---|---|
| M1 | `decision_unrecorded` and `internal_error` are 503 on the sandbox routes (`api/routers/sandbox.py`) | `tests/e2e/test_sandbox_runs.py::test_m1_a_fault_on_the_sandbox_routes_is_the_standard_503_not_a_policy_denial` |
| M2 | `set-policy` refuses unknown tool names (`gateway/admin.py`, `KNOWN_TOOLS`) | `tests/integration/test_tool_argument_deny.py::test_m2_set_policy_refuses_a_tool_name_the_platform_does_not_have` |
| M3 | No `pattern`, `patternProperties` or `format`; check runs in a thread with a 0.25 s limit, a timeout is a deny (`gateway/policy.py`) | `tests/unit/test_sandbox_qa_fixes.py::test_m3_a_schema_with_a_regex_is_refused`, `::test_m3_a_slow_check_is_a_deny_and_does_not_stall_the_event_loop` |
| L1 | One deny row per token, path and minute for out-of-run uses, via a Redis counter (`api/auth.py`) | `tests/e2e/test_sandbox_runs.py::test_l1_a_leaked_token_writes_one_deny_row_per_path_per_minute_and_is_refused_every_time` |
| L2 | `agent_reported` in the stored result and runs API; usage flagged (`api/agent/response.py`, `schemas.py`) | `tests/unit/test_sandbox_qa_fixes.py::test_l2_a_sandboxed_answer_marks_what_the_agent_wrote_itself_and_an_in_process_one_does_not`, `tests/e2e/test_sandbox_runs.py::test_l2_the_runs_api_and_the_stored_result_mark_the_agents_own_fields` |
| L3 | `network_denied` keeps host, port, reason (`adapters/sandbox_events.py`) | `tests/unit/test_sandbox_qa_fixes.py::test_l3_a_refused_connection_keeps_host_port_and_reason_and_nothing_free_form` |
| L6 | Token records its key; refused once the key is revoked (`core/identity/run_tokens.py`, `Principal.credential_id`, migration `0010`) | `tests/integration/test_run_tokens.py::test_l6_a_run_token_ends_when_the_api_key_that_started_the_run_is_revoked`, `tests/e2e/test_sandbox_runs.py::test_l6_the_sandbox_routes_refuse_a_run_token_once_its_key_is_revoked` |
| L4, L5 | Accepted. Runbook ("Accepted risks") and `RISKS.md` S9-9, S9-10 | none |

Existing expectations that changed on purpose: the probe-derived `network_denied` row now holds host, port and reason `agent_check` (`test_openshell_runtime`), the migration test lists the new `key_revoked_at` column, and a Vitest fixture gained `agent_reported: []` (type only).
Numbers: backend 1523 passed, 10 skipped (+19); Vitest 207; Playwright 82; ruff (with `sandbox_agent` and `scripts/eval`), mypy (146 files) and the DDL guard clean; `check_skips.py --expect 10` passes. OpenAPI snapshot and the UI schema were regenerated for `agent_reported`.

## 8. Where the facts are
`docs/runbooks/openshell.md` has the pinned versions with SHA-256 and source URLs, the requirements, the install steps, the images, and what the live run showed (binary identity, the 19-character name limit, baseline read paths, no event for a refused read, exit 137 for the memory limit). ADR-0009 (the OpenShell section) has the decisions.
