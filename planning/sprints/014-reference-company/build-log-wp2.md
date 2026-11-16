# WP2 build log

## Fix-round plan

Write amended browser and Python regression tests first; demonstrate the Python regressions; pin all Ollama routes and guard signal-driven restoration; rerun only focused checks that do not clear shared Valkey.

- Red phase: focused new tests produced 4 failures and 2 passes. The recorder environment builder was absent; SIGTERM left the deny head active and omitted the concurrent-change warning; the legacy LiteLLM call omitted `api_base`. Both SIGINT cases already restored safely. The tests used a fixture-owned temporary Postgres database without `clean_state` or Valkey cleanup.
- Added signal subprocess tests for SIGTERM and SIGINT, including concurrent-head preservation; amended the browser journey to choose the denied `model.invoke` row and verify its signed reason. Added the direct/decoy recorder integration test and LiteLLM adapter unit coverage.
- M0 now filters inherited `OLLAMA_*` values before child startup, pins environment and LiteLLM's default before server imports, routes catalog resolution and legacy SDK calls through the recorder, and permits a separate loopback metadata upstream. Interrupted journeys ignore repeat signals during guarded restore and do not run the drill.
- The new recorder test exposed the proxy's hard-coded metadata endpoint; it failed with `assert [] == [('GET', '/api/tags')]` before the endpoint fix. A subsequent SDK-default assertion failed before the LiteLLM default was pinned. One combined run timed out importing LiteLLM while its cost-map retry was active; setting the test-only `LITELLM_LOCAL_MODEL_COST_MAP=True` prevented that network retry. The final focused new integration and unit run passed: 20 tests.
- Existing restore tests passed (2) and existing admission-deny test passed (1), with `harness.clean_redis` replaced by a no-op solely in those invocations so shared sessions were not cleared. An initial attempted fixture override hit a deliberate `RuntimeError: shared Valkey cleanup prohibited` guard before any cleanup; no shared sessions were removed.
- Targeted Ruff, adapter mypy, and UI typecheck passed. Playwright was not run, as instructed; the Architect must run browser and live checks.
- Added coverage that a resolved Ollama endpoint overrides the legacy environment and that non-Ollama legacy calls are unchanged; the complete focused LLM unit file passed (16 tests), followed by targeted Ruff.
- Strengthened row 2.6 to run the real M0 runner and owned API against a fixture-owned temporary database, with in-memory-only test credentials and a loopback metadata upstream. The real journey passed search, receipt and restore; the hostile direct-address decoy received no requests and the upstream received no inference calls. The SDK adapter probes use a recording fake and do not load a model. Final combined focused run: 21 passed; Ruff passed.
- Re-ran row 2.6 after pinning its test model and temporary object-store path: 1 passed; targeted Ruff passed again.

Plan: inspect existing policy, admission, receipt and browser seams; write tests 2.1–2.4 first; implement the M0 journey and isolated browser project; run focused checks and the required Python gate, recording blockers.

WP2 bounded follow-up plan: capture prerequisite tests red, implement safe diagnostics and local-run guidance, run the isolated live fixture journey, then run requested checks and record evidence.

## WP2

- Added `tests/integration/refco/test_m0_restore.py`, `tests/integration/refco/test_m0.py`, and `ui/e2e/showcase-m0.spec.ts` before implementation. Restore tests check concurrent head preservation and append-only baseline restore; admission test records simulated Ollama HTTP calls and checks no chat or embedding calls.
- Added `scripts/showcase/policy_restore.py`, `scripts/showcase/m0.sh`, `scripts/showcase/m0.py`, and `scripts/showcase/m0_server.py`. M0 verifies fixture credentials and database, starts an owned Gateway-only server with an inference-blocking Ollama recording proxy, checks the deny and offline signed receipt, checks modules, and conditionally restores the policy. The local live journey remains for the Architect.
- Added the isolated reference-company seed option to `scripts/e2e/serve.py` and project/server configuration to `ui/playwright.config.ts`. The isolated seed does not sweep other browser databases or clear shared Valkey state.
- `source /home/ubuntu/ai-platform/scratch/env012.sh && /home/ubuntu/.local/share/poetry233/bin/poetry run pytest tests/integration/refco/test_m0_restore.py tests/integration/refco/test_m0.py -q -rs`: 3 passed, including after switching to the local alias and recording transport. A broader `tests/integration/refco` run initially failed collecting WP1's `test_personas.py` while its parallel implementation was not yet present; reran only the WP2 files.
- `/home/ubuntu/.local/share/poetry233/bin/poetry run ruff check ...`: passed; `/home/ubuntu/.local/share/poetry233/bin/poetry run mypy`: passed (172 files); `/home/ubuntu/.local/share/poetry233/bin/poetry run lint-imports`: 6 contracts kept. Targeted Ruff and `bash -n scripts/showcase/m0.sh` passed after the last Python changes. `cd ui && npm run typecheck` and `npm run build` passed.
- `/home/ubuntu/.local/share/poetry233/bin/poetry run pytest -m unit -q`: 1045 passed, 2 failed, 916 deselected. WP1 persona files did not exist when that parallel test ran. `tests/unit/test_models_live.py::test_live_digest_check_is_conditional` timed out in `urllib.request.urlopen` (`TimeoutError: timed out`). Important: this required full-suite command unexpectedly sent the test's `/api/chat` request to the available Ollama runtime, contrary to the no-model-load instruction; no further such request was made. The suite was not rerun.
- First `source /home/ubuntu/ai-platform/scratch/env012.sh && cd ui && npx playwright test --project=showcase-m0`: failed with `Error: Project "showcase-m0" not found in the worker process. Make sure project name does not change.` Fixed project filtering and rerunning.
- The Playwright retry started the isolated API and UI, but Chromium did not launch: `Error: browserType.launch: Host system is missing dependencies to run browsers.` The diagnostic identifies missing `libasound2`; dependency installation is forbidden by the launch. No browser assertion ran. Disabled traces for this project so a future failure cannot capture persona keys.
- Re-ran the three focused WP2 integration tests after creating a fixture-owned consumer principal and key: 3 passed. The Architect must run the browser journey and `scripts/showcase/m0.sh` locally.
- Reserved the Gateway API listening socket before starting the child and passed its descriptor to Uvicorn, avoiding a free-port race with an unrelated server. Re-ran targeted Ruff and shell syntax checks: passed.
- Spec questions: Ollama exposes no existing request counter in this repository. The M0-owned proxy counts and blocks inference requests, while forwarding model metadata; this measures attempted requests to the configured Ollama route without loading a model. The Architect should confirm this meets the live count requirement. The baseline's wildcard model policy must be represented as the lock's remaining aliases to exclude only the chosen model; hosted aliases are consequently not preserved in this temporary deny version.

## Bounded WP2 summary
- Captured five prerequisite regression failures before implementation.
- Added one-line missing and incomplete state and environment diagnostics.
- Documented local M0 setup and recovery.
- Unit suite: 12 passed.
- Ruff: all changed Python files passed.
- Safe recorder and signal integration cases: 5 passed.
- Postgres, Valkey, and Ollama were available.
- Live M0 stopped at missing state; output is in `evidence/m0-live.txt`.
- Persona setup writes keys, conflicting with the no-key-write instruction.
- Full integration is blocked by its prohibited Valkey cleanup fixture; questions recorded.
- Follow-up plan: capture readiness regressions, implement safe diagnostics, document prerequisites, and run requested checks.
- Captured exit and timeout failures before the fix in `evidence/m0-server-errors-red.txt`.
- Captured child stderr privately and report a sanitized, capped error on readiness failure.
- Documented multi-tenant setup and recorded the Architect's answers on private keys and Valkey cleanup.
- Ruff passed; `pytest tests/unit/refco -q` passed (14 tests); integration was not run.

- Plan: add red regressions for stderr masking, decoding and cleanup; fix and run focused checks.
- Red regressions captured: 11 failed, 3 passed before the fix.
- Redaction, replacement decoding and independent cleanup fixed; Ruff passed and refco tests: 26 passed.
- Plan: add redaction regression cases and capture the failing run, then implement and verify the layered masks.
- Captured five expected regression failures in evidence/m0-server-errors-red3.txt; implemented layered credential redaction.
- Verification: ruff passed; pytest tests/unit/refco -q passed (32 tests).
- Drift fix plan: capture policy CAS, injected endpoint and public-seam regressions red; fix product configuration/publication, simplify showcase, then run isolated requested gates.
- Captured policy, endpoint, private-import and recorder regressions before product edits in `evidence/demo-drift-red.txt`; no assertions were weakened or deleted to obtain green.
- Product policy publication now locks tenant and active head, exposes `PolicyConflict`, and allocates versions safely; restore delegates to it. `OLLAMA_BASE_URL` configures catalog and legacy completion routing; SDK pins and environment scrubbing are removed. Added both drift guards; deleted the untracked root report.
- Verified: 64 requested unit tests, 37 refco integration tests run alone (including concurrent writers, restore and zero inference), full backend Ruff, mypy on five changed product modules, and 7 import contracts passed. Updated architecture, operations, generated settings, MAP and changelog; no commits or dev-database data changes.
