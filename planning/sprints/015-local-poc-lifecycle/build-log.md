# Sprint 015: Build log

## Plan
- Read the current planning authority and verify the named code seams.
- Rename the pack and replace its contracts with the approved local lifecycle.
- Specify tests before implementation, an evidence runner, and model-routed launches.
- Check document consistency, shell syntax and change scope; write the handoff report.

## Drafting findings
- Planning only: no product, test or Compose changes, installs, builder launches or commits.
- `git mv` failed: the linked worktree index is outside the writable workspace. Moved the directory on disk; the owner stages the rename.
- API is absent from Compose. Worker has a healthcheck but lacks the requested hardening.
- Dockerfile uses Poetry at build time, not a wheelhouse. Keep that method; the old wheelhouse requirement was unsupported.
- Local receipt keys are ephemeral; settings accept inline keys only. API and purge worker need the same persistent secret.
- Objects are immutable SHA-256 files; jobs and outbox are durable in Postgres. Purge has no backup lock.
- M0 exists: its shell wrapper delegates to Python, where the restore-drill SKIP lives.
- Reference-company seeding denies all models, Playwright pins a host Poetry path, and legacy citation generation permits an ungoverned fallback.
- The new pack removes the maintenance exception and private-key-in-data-backup contract.
- Unresolved policy and ownership choices are in `planning/QUESTIONS.md`; fallbacks refuse unsafe operations.

## Draft validation
- Shell syntax and both embedded Python blocks compile. All 24 threat nodes match the 36 named pytest nodes.
- MAP is within its limits, old-slug references are gone, and only planning paths changed.
- Captured output: `evidence/draft-checks.txt`. Product acceptance and baseline remain unrun.
- The final runner rejects skipped/missing drill steps and runs combined unit/integration/e2e checks with the exact existing skip allowlist.

## Pre-start review application
Plan: apply R1–R5 to the pack and decisions, add the standing review step, then check test nodes and shell syntax.
Applied R1–R5, resolved both inputs and added the standing review step. Checked the threat-model node subset and `bash -n`; both pass. No implementation or live acceptance was run.
- 2026-11-17 02:49:46 Architect: the baseline ruff rc=1 came from the pack linting the legacy `scripts/labs` (464 errors, out of scope). The ruff scope is fixed to the CI dirs plus the new 015 script dirs; re-run, all checks passed.

## WP0 builder plan
- Write specified WP0 tests and capture their red output before implementation; reproduce the settings isolation failure.
- Implement explicit journey policy cleanup, environment-based Poetry resolution and mandatory governed model calls; preserve regressions.
- Run WP0 and static checks, capture evidence and report any unavailable live checks.

## WP2 plan (approved builder)
- Follow pre-start-review overrides; preserve the existing dirty planning worktree.
- Write all named WP2 tests, run them, and capture red output before implementation.
- Add exclusive private-file creation, validated file-backed Settings, shared secret mounts,
  and exact public-key restore checks; document separate offline private-key recovery.
- Run focused and regression checks, record unavailable live lifecycle evidence as pending.
- WP1 is absent here (no poc runner or API service); do not implement WP1/WP3 in this launch.

## WP0 red checks
- `poetry run pytest -q tests/unit/test_settings_modules.py tests/integration/refco/test_m0.py -k test_all_is_the_default_and_gateway_is_mandatory`: 1 failed, 17 deselected; `DEPLOY_SHAPE` is `multi_tenant` instead of the asserted code default. Captured in `evidence/wp0-settings-red.txt`. An earlier attempt naming `tests/conftest.py` as a test had an import mismatch; the mixed-tier run reproduced the actual defect.
- `poetry run pytest -q tests/unit/test_llm.py -k 'missing_govern' ...`: 8 failures: both functions reached the provider with missing caller/context. Captured in `evidence/wp0-red.txt`. The `-k` selection excluded the other specified tests; they still need an independent red run.
- Additional red run (`evidence/wp0-other-red.txt`): Poetry path and seeded deny failed as expected; two policy restore cases and alias policy test passed; the first citation integration setup failed on a fake catalog use mismatch, so it does not establish a product regression. Reworked that test to use real database decisions and cover retries, denial and write failure; it needs a rerun.
- Mixed-tier settings green: `evidence/wp0-settings-green.txt`, 1 passed, 17 deselected. The assertion is unchanged and `Settings(_env_file=None)` excludes env-file leakage.
- After the red runs, removed the ungoverned provider fallback, removed the reference-company seed deny and began environment-based Poetry resolution. The existing legacy semantic regressions still need migration to a governed caller; this work is not yet verified.
- Citation test rerun against live fixture: `evidence/wp0-citation-red.txt` reports 1 passed, including recorded retries, policy deny and decision-write failure; the pre-existing governed path already met this assertion.

### WP2 tests first: RED, before implementation
- Added the six exact WP2 nodes from test-spec (unsafe-file cases parameterized).
- Command: prepared Poetry 2.3.3 `run pytest -q --tb=no tests/unit/test_poc_keys.py tests/unit/test_settings.py tests/integration/poc/test_keys.py tests/integration/poc/test_restore.py::test_wrong_key_id_requires_previous_public_key`.
- Captured `evidence/wp2-red.txt`: **17 failed, 27 passed**. Missing key/recovery modules
  and ignored file setting are expected failures; existing Settings assertions passed.
- `--tb=no` prevents test-generated private material appearing in assertion output.
- Baseline accept.sh launched before code. Existing WP0 edits appeared concurrently;
  preserve them. Baseline ruff/licence/image scan already fail, outside WP2.
- Prepared Poetry found at `/home/ubuntu/.local/share/poetry233/bin/poetry`;
  no installs. Docker responds, but image scans fail in WSL credential helper.
- `m0_policy.py --help` exposed that running the helper by path cannot import the project; the browser now invokes it as `python -m scripts.showcase.m0_policy`. The first ruff run found three import-order errors; fixed and reran successfully (`evidence/wp0-ruff.txt`). Mypy and all 7 import contracts pass (`wp0-mypy.txt`, `wp0-imports.txt`).
- The browser red run reached the eval gate and exposed another legacy ungovened call in `scripts/eval/suite.py`; evidence `wp0-browser-red.txt`. The offline fake eval setup now uses ModelCaller, a fake catalog, fake limits and a decision sink. Manual real eval now needs a real governed context and is not run; no paid provider was called. The pre-existing unit network-guard regressions also call the old signature and need governed setup.

### WP2 implementation and first green
- Added `scripts/poc_lib/keys.py`: private no-follow directories, owner/mode/type/link
  checks, directory lock, atomic no-replace publication, retained host key/password,
  public-only identity and identical API/worker read-only bind fragments.
- Settings validates and caches file material in a private SecretStr attribute;
  serialization contains only the path. Inline/file ambiguity refuses startup.
- Added exact public-bytes/id restore validation, including rechecking missing/changed
  active files; local ephemeral fallback is never accepted by recovery validation.
- `.poc/` is excluded by git and Docker. No secrets exported or subprocesses launched.
- First green command (same unit files plus restore-key node): **43 passed** in
  `evidence/wp2-first-green.txt`; focused ruff passes. No assertion was weakened.
- Integration fixture corrections: explicitly wire the fresh Settings into the API's
  cached composition root, select the throwaway app DB, request the real `chat` port,
  and create an audit-scoped credential through public admin functions.
- WP0 package command passed 74 tests (`evidence/wp0-tests.txt`); focused unit/network regression passed 42 (`evidence/wp0-unit.txt`), and the offline eval gate preserved all baseline scores (`evidence/wp0-eval.txt`). Retry regression now asserts ModelCaller's 0.25-second bounded first backoff, two/three attempts and sanitized failure instead of the removed 35-second fallback.
- Scoped ruff passes (`evidence/wp0-ruff-scoped.txt`). The full ruff run also found an import-order issue in concurrently present `tests/integration/poc/test_keys.py`, outside WP0; left that file untouched. The real-provider eval is fail-closed and requires a governed context; its paid verification is recorded in QUESTIONS.
- Exact WP2 command with prepared service ports now passes: **44 passed, zero skips**,
  `evidence/wp2-green.txt` and `wp2.xml`. The real API lifespan is recreated twice;
  a real worker purges in Postgres, and saved receipts pass the standalone verifier.
- Real Compose `config --format json` accepts both read-only key mounts and exposes
  no private bytes (`evidence/wp2-compose-render.txt`). These use fixture service
  definitions; this is not evidence of product containers running.
- Full mypy: 172 files pass; helper mypy: 6 files pass; all 7 import contracts pass.
- Baseline pytest's automatic assertion rendering exposed the deterministic synthetic
  Settings test sentinel in accept-unit.log/unit.xml. Replaced only that sentinel
  with an explicit redaction marker; counts and failures are unchanged. Focused red
  output used `--tb=no` from the start and needed no redaction. No real key was logged.
- The selected alias live check passed with zero provider calls (`evidence/wp0-alias.txt`). Replaced the original source-inspection seed check with a live `seed`/policy-version check; its result is recorded separately in `wp0-seed.txt`.
- The browser red command was launched before implementation but its server loaded files while they were changing, so its eval-gate failure is not a clean pre-change browser red. Do not treat it as one. Browser acceptance requires the later run and independent review.
- Live seed check passed (`evidence/wp0-seed.txt`): one initial policy version, models allowed.
- Browser rerun (`evidence/wp0-browser.txt`) reached migrations but did not reach health or produce a test result after more than four minutes; interrupted the stalled command. Browser acceptance remains pending, not PASS. The live seed and alias checks passed separately; independent review remains pending.

### WP2 regression evidence and limits
- Full unit tier: **1240 passed, zero failures** (`evidence/wp2-unit.txt`, `wp2-unit.xml`).
  Baseline unit tier was 1214 passed / 24 failed (15 WP2 reds and 9 other reds).
  Two further tests arrived from concurrent WP0 work, so that aggregate delta is not
  attributable to WP2 alone. The WP2 focused delta is exactly 17 failures → 0 failures.
- Strengthened secret capture to INFO logs plus stdout/stderr, blocking both run and
  Popen during lifecycle calls: **42 passed**, `evidence/wp2-secrets-final.txt`.
- Saved trusted public keys now come from the API and are written beside saved
  receipt artifacts; the standalone offline verifier uses only those saved files.
- Settings integrity: all 25 original tests and 39 original assertions retained;
  no WP2 skip/xfail (`evidence/wp2-test-integrity.txt`).
- A2 remains open for independent review and real container/down/up/data-snapshot
  evidence. WP1 must merge `StackSecrets.compose_override()` after its service
  overrides; WP3 must call `ensure_stack_secrets(..., restoring=True)` on recovery,
  retain the host .poc tree, and run `validate_restore_key` before starting writers.
  Their runners/services are absent here. No lifecycle/browser PASS is claimed.
- Product operator docs and generated settings reference updated; MAP/CHANGELOG/full
  acceptance belong to WP4. Concurrent WP0 edits were not changed by this builder.

### WP2 path review: extra red before correction
- Found a path-normalization edge: `symlink/..` was collapsed before no-follow
  traversal. Added `ancestor-dotdot-link` to the unsafe-file regression cases.
- Before the fix: **1 failed**, captured in `evidence/wp2-dotdot-red.txt`.
- Preserve lexical path components during traversal so the symlink is rejected
  before `..` is processed. Existing assertions remain intact.

## WP0 fix round 1
- Plan: add regression checks for commit failure, startup, journey failure, pricing and Poetry; capture red, fix, rerun focused and static checks. Browser remains pending per Architect instruction; WP2 files excluded.
- Red: `evidence/wp0-fix1-red.txt` captures both the commit failure (journal lost and success printed) and unresolved default Poetry commands (2 failed). Moved restore unlink and success after transaction exit; resolved Poetry in all configurations.
- Additional no-network Docker fixture check passed using the prepared local app
  image (no pulls/builds). Both container readers loaded the same read-only-mounted
  key through production Settings twice; their identities matched. Fixture Compose
  resources were torn down, no data volumes used (`evidence/wp2-container-key-mount.txt`).
  These were key-reader commands, not the missing product API/worker stack.
- Final focused result with the extra symlink/.. case: **45 passed, zero skips**;
  initial 17 reds plus the separate additional red are resolved.
- Broader baseline all-tier run overlaps concurrent sprint work and is diagnostic,
  not a clean final acceptance run. Its pre-code unit output and focused red output
  are preserved; final WP2 checks run separately. No acceptance box is checked.
- Final unit rerun after the lexical-path fix: **1241 passed**, zero failures/skips
  (`evidence/wp2-unit.txt`, `wp2-unit.xml`). Full lint, mypy, helper mypy, import
  contracts and generated docs were rerun after that fix and pass.
- Baseline's licence collector fails; image pulls fail through the WSL credential
  helper. Its ambient Node was 20 (prepared Node 24 is available), so any baseline
  UI results need a prepared-Node rerun by the owning WP, not an acceptance claim.
- Coverage findings refer to tests, while startup, automatic cleanup, and pricing fallback were already correct in the current implementation. Their new tests therefore cannot honestly be red against unchanged production code. Sensitivity runs temporarily reintroduced the old startup deny, disabled cleanup, and zero-cost fallback; restored sources afterward. `wp0-fix1-flow-mutation-red.txt` records three failures (startup blocked before state and both cleanup cases); `wp0-fix1-pricing-mutation-red.txt` records the zero-cost failure. Separate startup mutation after ingest checks the history itself.
- Green so far: `wp0-fix1-green-initial.txt` (4 passed), `wp0-fix1-flow-first.txt` (3 passed); scoped unit/import checks `wp0-fix1-unit.txt` (91 passed); `wp0-fix1-ruff.txt`, `wp0-fix1-mypy.txt` and `wp0-fix1-ui-build.txt` pass. No browser run, per explicit instruction; browser acceptance and cleanup evidence remain pending Architect.
- `wp0-fix1-startup-mutation-red.txt`: the old post-ingest startup deny produces head version 2 instead of 1. `wp0-fix1-alias-mutation-red.txt`: accepting unknown aliases makes the governed denial assertion fail. Both mutations were confined to the test run and restored; these are mutation reds, not pre-change failures.

## WP1 (approved builder: Claude stand-in, Codex rate-limited)

Plan: tests first, record red, then add the `api` service and hardening, the POC override,
`scripts/release/build_manifest.py`, `scripts/poc_lib/{runner,up}.py` and the `scripts/poc` entry point,
a bootstrap helper, and fresh-db migrate. No live `up` while the dev Playwright run is active (see PENDING).
Reuse WP2 `ensure_stack_secrets` / `compose_override`; WP0/WP2 files untouched except as noted below.

### WP1 tests first: RED, before any product change
- Added `tests/unit/test_poc_compose.py` (3 nodes: default services+hardening, override resets, override requires port),
  `tests/unit/test_release_manifest.py` (4 nodes: the two named, hash coverage, real inputs),
  `tests/unit/test_poc_up.py` (extra: orchestration with a fake Runner), `tests/integration/poc/test_up.py` (the two named live nodes).
- Command: `$POETRY run pytest -q --tb=no tests/unit/test_poc_compose.py tests/unit/test_release_manifest.py tests/unit/test_poc_up.py tests/integration/poc/test_up.py`.
- Result (`evidence/wp1-red.txt`): the three new modules fail at collection (no `scripts.release`, `scripts.poc_lib.up`/`runner`);
  `test_poc_compose.py`: 2 failed (`test_default_services_and_hardening`, `test_poc_override_resets_names_and_ports`), 1 passed
  vacuously (`test_poc_override_requires_its_port`: the override file is absent so Compose fails; it is meaningful after the override exists).
  Existing `tests/unit/test_compose.py` 14 passed (it asserted the old three-service default; it is updated below to four).

### WP1 implementation and green
- Files added: `scripts/release/{__init__,build_manifest}.py`, `scripts/poc_lib/{runner,up}.py`, `scripts/poc` (entry:
  `poetry run python scripts/poc up <stack>`), `docker/poc.override.yml` (`!reset`/`!override`), `docker/poc-bootstrap.sh`.
  Files changed: `docker-compose.yml` (shared `x-app` anchor, new `api`, hardened worker), `Dockerfile` (`/data/objects` mode 1777 so the
  non-root host-uid process can write the object volume), `docs/operations.md` (short `poc up` section).
  WP2 `scripts/poc_lib/keys.py` is reused unchanged (`ensure_stack_secrets`, `compose_override`). No WP0/WP2 file edited.
- Tests (red then green): `test_poc_compose.py` (3), `test_release_manifest.py` (4), `test_poc_up.py` (extra, 19 cases: order, argv-only, no ambient
  profiles/project, no secret in argv, idempotent, bad names, remote Docker, foreign marker, stale manifest, unhealthy, offline index proof, Runner),
  `tests/integration/poc/test_up.py` (2 named live nodes, collect only; see PENDING). Green: 26 unit passed (`evidence/wp1-green.txt`).
- Existing tests updated, none weakened: `test_compose.py` default set now four services; `test_gateway_packaging.py` worker test reads parsed YAML
  (worker merges `x-app`) with the same assertions plus api build equality; `test_supply_chain_controls.py` renamed
  `..._keeps_only_api_worker_and_app_dockerfile`, expects built services `["api","worker"]`.
- Finding: Compose labels each service image, so api and worker image IDs differ though layers are identical (`evidence/wp1-image-ids.txt`). "One artifact" is
  therefore proved by the ordered layer-digest hash (`content_id`); per-service `image_id` is recorded too. The Docker store ID is a local image ID, never an index digest.
- Real evidence: 9 distinct external pins fetched with `docker buildx imagetools inspect --raw`; each is a multi-arch index whose bytes hash to its pinned digest
  (`wp1-index-proofs.txt`); real manifest built and verified against a real build of both services (`wp1-release-manifest.json`, `wp1-build.txt`);
  `docker compose config` render of base+override+key override: four services, only API published on 127.0.0.1, no container names, volumes project-named, uid 1000,
  read-only, cap_drop ALL, no key bytes (`wp1-compose-render.txt`). `check_pins.py`: pass (api now a built service, covered by `image_scan.sh` built-service loop).
- Gates (evidence/wp1-*.txt): unit tier 1269 passed 0 failed (before WP1 changes 1241 + 28 new/other); ruff CI scope pass; mypy 172 files pass + helper dirs 6 files pass
  (`--explicit-package-bases`); lint-imports 7 kept; generated docs check pass.
- Design decisions: containers run as the host uid (`POC_UID/POC_GID`) so the 0600 key mount is readable after `cap_drop: ALL`; stack never reads `.env`/`.env.local`
  (`--env-file /dev/null`, `env_file: !reset []`); DB passwords stay the local defaults (database is not published); migration URL reaches `compose run` by name via env;
  `up --refresh-release` is the explicit way to accept a rebuilt image; restic service and `backup/down/status` are WP3.

### WP1 PENDING (not PASS)
- Live `poc up` (`tests/integration/poc/test_up.py`, both nodes), the `docker stats` capture for api/worker, the on-demand restic service stats, and a container start as uid 1000
  with read-only root: not run. A dev Playwright run was active and the brief forbids starting stack services or `docker run`. Architect runs `accept.sh` / that test file.
  Unverified live details: `compose run -e NAME` env inheritance, `compose up --wait` with the new healthchecks, API `/health` as uid 1000 with tmpfs HOME.
- `scripts/supply_chain/image_scan.sh` was not run (WSL credential helper fails image scans, per earlier baseline).

## WP1 fix round 1 (Claude stand-in builder)

### Red first (`evidence/wp1-fix1-red.txt`, 21 failed / 19 passed before any product change)
- Identity: new tests `test_repeat_up_accepts_a_rebuild_with_new_local_ids_but_the_same_content`, `test_content_id_*` (store ID, Compose labels
  and noise do not change `content_id`; layers, layer order, Entrypoint/Cmd/Env/User/WorkingDir/ExposedPorts/Labels do), the platform digest
  and ID-note test. Red because `inspect_local_image` hashed layers only and `verify_manifest` compared the store ID.
- Compose: `test_temp_files_live_on_a_volume_not_on_the_small_tmpfs` (KeyError TMPDIR), `test_bootstrap_keeps_the_password_out_of_argv` (red: `-v pw=`),
  `test_api_host_port_is_configurable_and_loopback_bound` (already green: `API_HOST_PORT` was in the compose file).
- Test edits forced by the decision, not weakenings: the FakeRunner/fixtures now return one JSON inspect document; the stale-manifest tests change
  layers/config (the old "image ID changed" case is now the accept case); `test_default_services_and_hardening` expects the extra `app_tmp` volume.

### Green and changes
- `content_id` = hash of ordered layers + Entrypoint/Cmd/Env/User/WorkingDir/ExposedPorts/Labels (no `com.docker.compose.*`). `image_id` stays, with
  `image_id_note`; `platform_manifest_digest` is recorded when the store reports a `Manifests` entry for the platform (not reported by the local store
  here, so unit-proved only). Never labelled an index digest. Repeat `up` now passes live.
- `app_tmp` volume at `/var/tmp/app`, `TMPDIR` set for api/worker, `/var/tmp/app` mode 1777 in the Dockerfile (same as objects); `/tmp` stays a 64m tmpfs.
  No upload size limit (backlog item for the Architect).
- Docs: getting-started and deployment (port 8000 sharing, `API_HOST_PORT`, TMPDIR); operations (content_id, ambient `APP_DB_PASSWORD`/`POSTGRES_PASSWORD`); comment in `compose_env`.
- Bootstrap: password read by `psql` from its environment (`\getenv`), no argv. Verified live (fresh stack created the `gap_app` role and logged in).
- Live test: new `test_worker_completes_a_durable_job_through_the_public_api` (key via owner-role admin functions in the app image, POST /v1/ingest, wait
  for `succeeded`, attempts 1). It uses a blank document: the stack has no model provider or tenant policy, so real embedding is denied (`model_not_allowed`
  seen live). Fixture tears down its project, `.poc/<stack>` (shutil.rmtree) and `ai-platform-poc-<stack>-{api,worker}`. Stats go to pytest tmp_path.
- Restic stats line: PENDING (WP3).
- Evidence: `wp1-fix1-live-up.txt` (3 passed), `wp1-fix1-unit.txt` (1283 passed), ruff CI scope pass, mypy 172 + 6 changed files pass, lint-imports 7 kept.
- PENDING: a leftover `.poc/t62e97696` from an earlier failed live run was removed by shutil. `image_scan.sh` not run.

## WP3 (approved builder: Claude stand-in, Codex rate-limited)

Plan: tests first and recorded red, then the shared purge lock, the Runner contract (spawn, file output), the pinned restic
profile, one staged snapshot, checked `down`, restoring `up`, `status --json`. Reuse WP2 key helpers and WP1 `up`/Runner/manifest.
Design points: (1) the backup lock is a Postgres advisory lock held by a long-lived `psql` inside the postgres container
(Postgres is not published on a POC stack); purge takes the same key shared, inside its transaction. (2) `POC_RECOVERY_REF`
is the snapshot id (full or 8+ character prefix). (3) `.poc/<stack>/latest.json` is the published pointer; it moves only after
restic has stored the snapshot and the manifest hash read back from restic equals the staged one.

### WP3 tests first: RED, before any product change (`evidence/wp3-red.txt`)
- Added: `tests/unit/test_poc.py` (stack name x command, remote/missing marker, foreign marker, Runner, `down` order, writes
  after backup, stale backup, recovery ref, destroy ownership: 6 test functions, parametrized), `tests/unit/test_poc_backup.py`
  (restic contract, one-snapshot pipeline, failed dump/restic/cancel/lock never publish),
  `tests/integration/poc/{conftest,test_backup,test_restore,test_down}.py` (live nodes named in test-spec).
- Result: both unit modules fail at collection (no `scripts.poc_lib.lifecycle`, `scripts.poc_backup.model`);
  the poc integration conftest fails to import, so every live node errors. No product code was changed before this run.

### WP3 implementation and green
- Added: `core/database/locks.py` (shared/exclusive advisory lock; purge handler takes it shared per batch), `scripts/poc_lib/{context,lifecycle}.py`,
  `scripts/poc_backup/{model,pg,restic,catalog,capture,verify,restore}.py`, restic service (profile `backup`, `restic/restic:0.19.1@sha256:1366...`,
  no network, no Docker socket) in `docker-compose.yml`; Runner gained `output_file`, `input_file`, `spawn`; `up` restores after `down`; CLI `backup|down|status [--json]`.
  `compose_env` gained optional `stack_dir` (sets POC_STACK_DIR for restic mounts). `tests/unit/test_compose.py`: `restic` added to NO_PROBE_SERVICES
  (one-off tool, profile-only, nothing depends on it); no assertion weakened.
- Tests added: unit `test_poc.py` (6 functions, 70+ cases), `test_poc_backup.py` (4 functions); live `test_backup.py` (3), `test_restore.py` (+5), `test_down.py` (2).
- Live results: `evidence/wp3-live-try2.txt` (backup+down: 5 passed), `wp3-live-restore-try2.txt` (6 passed: includes WP2 key test), `wp3-live-up-regression.txt` (3 passed).
  Earlier tries: `wp3-live-backup-try1.txt` (test bug: platform rate limit 429 from my own writer; fixed by pacing/retry), `wp3-live-restore-try1.txt` (test bug: restic packs are 0400).
- Mutation reds (`wp3-mutations-red.txt`): skipping the live-state gate, skipping `verify`, and a no-op purge lock each fail the named tests.
- Gates: unit tier 1361 passed (`wp3-unit.txt`); ruff CI scope pass; mypy on changed files pass; lint-imports 7 kept.
- PENDING / not done: key-mismatch and tampered-snapshot negatives were not mutation-tested (live, ~4 min each); full `mypy .` fails on a pre-existing tests/e2e conftest
  module-name clash, so only changed files were checked; `accept.sh`, `m0.sh`, image scan, docs (operations runbook, generated settings) and MAP/CHANGELOG are not updated (WP4);
  multiple processes losing power mid-`pg_restore` and a UTC-midnight crossing during the journey test are untested.

## WP3 fix round 1 (builder: Claude stand-in; Codex rate-limited; review verdict was CHANGES REQUIRED)

Tests first, product after. Every red below was run before the product change it covers (the live resume and kill-lock reds are in
`evidence/wp3-fix1-red-live*.txt`; the unit reds in `wp3-fix1-red-unit.txt`; the job-deferral reds in `wp3-fix1-red-defer.txt`).

### Reds recorded before any product change
- Unit (`wp3-fix1-red-unit.txt`): 25 failed + 1 collection error across `test_poc_restore_pending.py` (new, 16), `test_poc_backup.py`
  (+7: lock proof by pid and key, lock lost, psql died, lock-wait timeout, midnight x3; the backup-crossing-midnight test was added after the red run and was green at once, it pins existing behaviour),
  `test_poc.py` (gate 3 schema head and object list; volume removal failure), `test_purge_lock_wait.py` (new: collection error, `DeferJob` missing).
  Note: the first red run for `test_poc_restore_pending.py` also showed a fake-runner flaw of mine (every `up` ended "services not healthy": my fake swallowed the `ps` rows).
  I fixed the fake and re-ran before touching product code: 15 failed + 1 passed, now for the real reasons
  (`ImportError` for `pending`, `DID NOT RAISE` on the second `up`, marker missing, alembic ran, `AttributeError: spawn`, no `restore-pending.json`). That second run was not saved to a file.
  Reasons: no `restore-pending.json`, restoring decided before the lock (a `down` holding the lock was not seen: alembic ran on an empty database), `rm` failure ignored.
- Jobs (`wp3-fix1-red-defer.txt`): the purge job went `dead` after 3 lock timeouts (only 3 timeouts seen, then no more attempts); `jobs.defer` and `DeferJob` did not exist.
- Live kill-lock (`wp3-fix1-red-live.txt`): `DID NOT RAISE`; a backup whose lock session was killed mid-dump still published a snapshot.
- Live resume (`wp3-fix1-red-live-resume.txt`): after the injected `pg_restore` failure there was no `restore-pending.json`.

### What changed and why
1. CRITICAL, a failed restore never lets `up` start an empty stack. New `scripts/poc_backup/pending.py` (atomic write: temp file, fsync, rename,
   directory fsync, mode 0600; strict reader, an unreadable or unsafe marker refuses and is never ignored). `up` decides `restoring` inside the stack lock
   (marker present, or marker.json + latest.json + no runtime volumes); with no marker it resolves the latest verified backup and writes the marker
   BEFORE `up postgres valkey` creates any volume. With a marker it resumes: the snapshot is the one the marker names (never `latest`); it must still be in
   restic and its manifest must hash to the marker digest, else a clear refusal and nothing is removed; then `stop api worker`, `down --remove-orphans`
   (no `--volumes`) and removal of only this stack's three marker-listed volumes by exact name after the label and driver checks, then the restore runs
   again. The marker is cleared after the report is written and before api and worker start. `backup` and `down` refuse while it exists (`status` shows it).
   The normal path (alembic) is never taken while the marker is present. Fault seam for the live test: the public `Runner` (a wrapper that runs the real command and then fails it).
2. HIGH. `_restoring` and the secrets decision now run inside the lock. A first `up` (no folder) creates the folder and secrets first, as before. Unit test: a `down` that holds the lock finishes, then `up` restores.
3. MEDIUM. `pg.take_backup_lock` returns a `BackupLock` that remembers the lock session's backend pid; `capture` calls `assert_held` before it closes the session and
   before restic and the pointer: the psql client must be alive AND `pg_locks` must list that pid as granted holder of the advisory key (classid, objid, objsubid 1).
   Otherwise `PocError`, no snapshot, no `latest.json`. Live tests use the real psql-session lock: a purge job claimed by the stack's own worker waits while it is held and
   completes after release; terminating the lock's backend (test-only runner seam, just before `pg_dump`) fails the backup, leaves `latest.json` and the repository unchanged.
4. MEDIUM. New `scripts/poc_backup/volumes.py`: `down`/destroy and the resume path tolerate no failed `docker volume rm`. Every removal is tried, then each name is inspected;
   a failed removal, or a volume that is still there, fails with the names. Only volumes present at inspect time are removed (an absent one is not an error).
5. MEDIUM. `purge_guard` reads the transaction's previous `lock_timeout`, bounds only the wait for the shared lock, then puts the previous value back (plan and batch statements are not cut short).
   A general seam: `workers.types.DeferJob(code, delay_seconds)` and `jobs.defer()` (back to `queued` for later, `attempts - 1`, so the attempt is not used; the loop handles it, the queue has no purge special case).
   The purge handler turns `BackupLockTimeout` into `DeferJob("backup_in_progress", DEFER_SECONDS=60)`. Integration tests: 6+ consecutive lock timeouts leave the purge job `queued` with `attempts <= 1`, never `dead`,
   and after the lock is released the same job succeeds and purges; a handler that raises `DeferJob` is deferred five times with `max_attempts=2` and is not dead.
6. MEDIUM (test gap). `test_manifest_digest_binding_is_enforced_on_real_snapshots` (live, real restic): a manifest edited inside a real stored snapshot (tag kept), a truncated `latest.json`, an edited digest,
   `latest.json` naming an older real snapshot, a snapshot without its manifest tag (the "incomplete" branch), a non-JSON manifest, a manifest missing fields. `latest_ref`, `restore_latest` (with and without a pinned `ref`),
   `verify_snapshot` and `load_manifest` refuse each. Mutation proof: `evidence/wp3-fix1-mutation-digest.txt` (see below).
7. LOW. (a) A lock-wait `TimeoutError` becomes the same clean `PocError` ("could not take the backup lock in time"); a unit test. (b) `down` gate 3 also compares `schema_head` and the object list
   (the old unit case that expected a different object list to pass was an encoding of the old behaviour; it now expects refusal, and a reordered equal list still passes).
   (c) `restic` moved from `NO_PROBE_SERVICES` to `ONE_SHOT_SERVICES` in `tests/unit/test_compose.py`, because it is a one-off `run --rm` command that must never restart: the one-shot branch asserts `restart: "no"`,
   which the no-probe branch did not, so the move is stricter; `docker-compose.yml` gained `restart: "no"` on `restic`. No assertion was loosened.
8. Pending item, UTC midnight and the counters. `restore_latest` takes one clock reading when it starts and decides the counter day from it (it used to read the clock after the long restore: a restore begun on the manifest's day
   but finished after midnight lost its counters). `apply_counters` now tops a counter up with `INCRBY` by the missing amount (`captured - GET`), so a resumed attempt never doubles it and spend recorded since is never lowered.
   Unit tests with an injected clock: a restore crossing midnight applies exactly once (and twice in a row stays equal); a restore starting after midnight applies none; a partial or higher counter is topped up or kept;
   a backup crossing midnight keeps the date and key pattern of the day it started. Live: a resumed restore (after a fault injected AFTER the counters were applied) leaves the daily counter exactly equal to the captured value.

### Test changes that are not additions (none weakens a check)
- `tests/unit/test_poc_backup.py` fake lock session now prints a backend pid before `LOCKED` and answers the `pg_locks` query (the lock protocol gained the pid line).
- `tests/unit/test_poc.py` `VolumeDocker` now deletes a volume on `rm` (needed to model "gone"), and takes `fail_rm`/`ghost`. The object-list case described in 7(b).
- `tests/unit/test_poc_up.py`: the `repo` fixture body became `make_repo()` so the new file can reuse it (ruff F811); behaviour unchanged.
- `tests/integration/poc/conftest.py`: `seed_decisions(..., ages_days=...)`.
- The live purge-wait test is placed before the other decision-writing tests of the module: a purge deletes a chain prefix, so old rows seeded behind newer ones would never be purged (try 1 failed for exactly that reason, see `wp3-fix1-live-backup-try1.txt`).
- The counter-fault live step accepts `CommandError` as well as `PocError` (try 1 of `wp3-fix1-live-restore-try1.txt`: the CLI reports both as a refusal).

### Results (evidence in `evidence/wp3-fix1-*.txt`)
- Unit tier: 1389 passed (`wp3-fix1-unit.txt`); ruff CI scope pass (`wp3-fix1-ruff.txt`); `mypy` 173 files pass (`wp3-fix1-mypy.txt`), the host scripts (`scripts/poc_lib`, `scripts/poc_backup`, not in the mypy file list) pass with `--explicit-package-bases`
  (`wp3-fix1-mypy-scripts.txt`); `lint-imports` 7 kept (`wp3-fix1-imports.txt`). Regression integration: `test_retention`, `test_jobs`, `test_worker_process` pass; `test_job_defer` 3 passed (`wp3-fix1-green-defer.txt`).
- Live: `test_backup.py` 5 passed (`wp3-fix1-live-backup.txt`; try 1 `-try1`: 1 failed, my test ordering, fixed); `test_down.py` 2 passed (`wp3-fix1-live-down.txt`); `test_restore.py` 8 passed
  (`wp3-fix1-live-restore.txt`; try 1: 1 failed, my test expected `PocError` where the injected fault surfaced as `CommandError`); `test_up.py` 3 passed (`wp3-fix1-live-up.txt`).
  The live resume test shows: after an injected failure after `pg_restore`, and again after the counters were applied, `restore-pending.json` stays with the right snapshot and digest, no api or worker container ever exists,
  no `alembic upgrade` and no `up api worker` was issued, `backup` refuses and `latest.json` is unchanged; the third `up` restores from the same snapshot, counts, heads and checkpoints equal the manifest, the daily cost counter
  equals the captured value exactly, the marker is gone and the api container started after `verified_at`.
- Mutation (`wp3-fix1-mutation-digest.txt`, driver log `wp3-fix1-mutation-run.log`): each file copied to a temp location, the check replaced by `if False:`, the live digest test run, the file restored and compared with `cmp` (byte-identical every time).
  All three disabled: red (`DID NOT RAISE`). Each one alone: `latest_ref` red; `verify_snapshot` and `restore_latest` red (a different, later failure is raised instead of the digest refusal, so the digest-message assertion fails).
- Hygiene: no `ai-platform-poc-*` container, volume or `.poc/` folder left; the dev project and the volumes `ai-platform_pgdata` and `pgdata_trixie` were not touched; no commit, no stash.
- Not done / PENDING: `accept.sh`, `m0.sh`, the image scan and the docs/CHANGELOG are WP4. A power loss in the middle of `pg_restore` was modelled by a command failure, not a killed process. `purge_guard`'s timeout bound is verified by a recording fake plus the
  six-timeout integration test, not by a statement-level timeout probe on a live batch.


## WP4 (approved builder: Claude stand-in, Codex rate-limited)
Plan: close the three LOW findings of the WP3 fix-round review (tests first), write the four WP4 tests first, then the drill
(`scripts/verify/poc-drill.sh` over `scripts/verify/poc_drill.py`), wire it into `m0.sh <stack>`, close the product gaps the drill exposes, docs, live run.

### LOW findings (red: `evidence/wp4-low-red-unit.txt`; green: `wp4-low-green-integration.txt`)
- (a) `DeferJob`: a NaN, infinite or non-numeric delay raises `ValueError`; the delay is raised to at least 1 s (`jobs.bounded_defer_delay`, also applied in `jobs.defer`).
  Each deferral is counted: migration `0012_job_deferrals` (`jobs.deferrals INTEGER NOT NULL DEFAULT 0`, CHECK >= 0; the 0008 grants and RLS cover it),
  `JobRow.deferrals` (default 0), `Job.deferrals` in the API model (default 0; `docs/api/openapi.json` and `ui/src/api/schema.d.ts` regenerated), and the worker log line `deferral N`.
  Tests: `test_purge_lock_wait.py` (+10 cases), `test_jobs_units.py`, `test_job_defer.py` (live count), `test_migration_0012.py` (new, 3). `test_kafka_units.py::test_sprint_010_adds_no_migration` pinned head `0011`; it now pins `0012` (the head moved, the claim is unchanged).
  Existing live defer tests now wait the 1 s minimum per deferral (assertions unchanged).
- (b) `pg.py` lock-liveness query adds `mode = 'ExclusiveLock'`; asserted in `test_poc_backup.py`.
- (c) `up`: only the private stack folder is created before the lifecycle lock is opened (`keys.ensure_stack_directory`); the secrets are created under the lock. Two unit tests in `test_poc_up.py`.

### WP4 tests first (red: `evidence/wp4-red.txt`, `wp4-red-unit-product.txt`: collection errors, no product code existed)
`tests/unit/refco/test_m0_lifecycle.py::test_required_drill_failure_is_fatal` (+ 40 more cases: every step failing, teardown, tamper, counts/heads mismatch, entry path, shell entry),
`tests/integration/refco/test_m0_lifecycle.py::test_saved_receipts_and_new_call_after_restore`, `tests/unit/refco/test_public_seams.py::test_lifecycle_uses_public_seams` (+ seeded private import, SQL and SDK-override cases for Python and shell),
`tests/unit/test_poc_admin_destroy.py` (product gaps below).

### Product changes the drill needed (Rule 10: would a second client need this?)
1. `poc admin <stack> <identity command>`: yes. A POC stack publishes no database port, so no operator could create a key or publish a policy for it. Runs `scripts/admin/identity.py` in the app image; `--dsn` refused; DSN by environment name; policy on stdin.
2. `poc destroy <stack> --confirm <stack>`: yes. `down` keeps key, repository and marker by design; an evaluation that ends needs a supported total removal, not raw docker. Refuses foreign volumes and symlinked folders; found live: the `app_tmp` scratch volume was not in the marker, so `destroy` now removes it too (name and label proven).
3. `poc status --json` lists the latest backup's chain heads and checkpoints: yes. Any operator comparing a restore with its backup needs them.
4. The journey (`m0.py`) no longer runs the drill after a failed journey (it prints `INFO`, exits nonzero): a failed journey must not start a multi-minute stack build.
5. Drill finding: a fresh POC stack has no local model runtime, so the first governed search is denied at admission as `model_digest_mismatch` (the gateway checks the model digest before the policy). The drill therefore accepts either admission denial (`model_not_allowed` or `model_digest_mismatch`) and requires a recorded decision, a signed receipt and phase admission (no model reached). On a machine with a reachable runtime the alias deny is `model_not_allowed`. Not a product bug; stated so the report does not overclaim an alias-policy deny on the bare stack. The journey in `m0.py` (gateway-only API with the recorder and the real Ollama) still proves the alias deny with an exact zero request count.
6. `tests/unit/refco/__init__.py` added: the two files named `test_m0_lifecycle.py` (unit and integration) clash on module name under pytest's default import mode. `tests/integration/refco/test_m0.py` stubs `finish_with_drill` in its journey subprocess (assertions unchanged): it tests the journey, and the drill has its own live test.

### Results (evidence in `evidence/wp4-*`)
- Live drill alone (3rd try, `bash scripts/verify/poc-drill.sh m0drill`): all steps PASS, `tables=19 rows=26 heads=1 checkpoints=1`. Tries 1 and 2 failed at "deny receipt saved" (`model_digest_mismatch`, see 5); each tore the fixture down (verified: no `ai-platform-poc-*` container, volume or `.poc` folder). An earlier accidental run of the real drill from a unit test (existing tests that call `m0.main()`) was killed and destroyed with `poc destroy`; found the `app_tmp` leak (product change 2).
- `bash scripts/showcase/m0.sh m0drill` -> `evidence/wp4-drill.txt`: journey PASS lines, then every drill marker, `PASS restore drill`, exit 0. Used a throwaway database `gap_m0fx_*` on the dev Postgres server (tenant `m0fixture`, personas via `setup_personas.sh`, `.showcase/` in the worktree); both removed afterwards.
- Unit tier: 1517 passed, 1 failed (docs link check on `manifest.json` words in operations.md, fixed, 7 passed on rerun) (`wp4-unit.txt`).
- `pytest tests/unit/refco tests/integration/refco` (includes the live lifecycle test): `wp4-refco.txt`. ruff CI scope pass; `mypy` 173 files pass; host scripts mypy pass; `lint-imports` 7 kept; `check_no_ddl` ok.
- Not done: full `accept.sh` (Architect), browser project, image scan. MAP, CHANGELOG, report untouched. No commit.

## WP4 fix round 1
Plan: add regression tests and record red results; fix lifecycle ownership and locking, policy-deny evidence and seam scanning; run requested checks and live preflight, recording any blocked steps.
- Tests first: `pytest -q tests/unit/test_poc_admin_destroy.py::test_lifecycle_lock_is_outside_stack_directory tests/unit/refco/test_public_seams.py::test_journey_sources_use_strict_scanner` returned `F.`: the lifecycle lock is still inside the deletable directory; seeded override detection passed. Further regression coverage remains to be added.
- Further red tests: `tests/unit/refco/test_m0_lifecycle.py::{test_probe_failure_never_starts_or_destroys,test_digest_mismatch_is_not_a_policy_deny}` both failed: the failed probe proceeded to `up`, and the digest mismatch passed. Stable-lock focused run exposed a test fixture creating `.poc` with unsafe permissions; correcting the fixture, not the safety check.
- Stand-in note: a Codex builder began this round (stable lock path, `wait=` on the lock, destroy under the lock, strict-scanner test) and was cut off. Kept as correct. Claude (stand-in) finished it.

### WP4 fix round 1: what changed per finding (Claude stand-in)
Red (tests first): `evidence/wp4-fix1-red-product.txt` (15 failed: create-only, owner token, StackAbsent/exit 3, token env wiring, destroy token). Drill tests were written after the drill edit (deviation, stated): mutants in `evidence/wp4-fix1-red-drill-mutants.txt` show 4 of 6 reverted behaviours go red (probe-as-absent, destroy without token, plain `up`, no inference check); the "phase default" and "digest accepted" mutants stay green only because `model["phase"]` and the later `reason != DENY_REASON` check fail the step anyway (redundant checks).
1. HIGH alias deny. No gateway change. A POC stack takes `POC_OLLAMA_BASE_URL` (`docker/poc.override.yml`: `OLLAMA_BASE_URL` for api and worker, `host.docker.internal` host-gateway). The drill starts `MetadataRuntime`: `GET /api/tags` from `models.lock` digests (so the chat alias resolves, no model contact), every other request refused 503 and counted. Hosted entries could not be used: `build_model_catalog` fixes every hosted scope to `unknown` (so `residency_unknown`), and the primary completion alias is admitted with use COMPLETION which hosted config never registers. Drill now requires exactly `model_not_allowed`, receipt phase `admission` (no default) and alias, runtime inference count 0 and `/v1/usage/summary` `totals.requests` 0 and `denied.policy` >= denies. `model_digest_mismatch` acceptance and both phase defaults removed. docs/operations.md drill paragraph rewritten.
   Second client need: yes. Any POC that wants a model (host Ollama) needs `POC_OLLAMA_BASE_URL`; no product code serves fake data, the stub lives only in the drill.
2. HIGH ownership. `poc status` exits 3 only when no `.poc/<stack>` exists (`StackAbsent`); other failures exit 1 and the drill aborts. `poc up --create-only` (under the lock: refuses with exit 2 if the folder or any project volume exists; needs `POC_OWNER_TOKEN`, writes `owner.token` 0600 first). `destroy` checks the token (constant-time, before any removal) when `POC_OWNER_TOKEN` is set; the drill always sets it. The token travels in the environment only. Unit tests: probe failure aborts, a pre-existing stack is never destroyed, a creator racing between probe and up makes create-only refuse and is never destroyed, token mismatch refuses.
3. HIGH destroy lock. Lock file `.poc/.locks/<stack>.lock`, held through all removals; state revalidated after acquiring. `test_destroy_holds_its_lock_through_deletion_so_a_waiting_up_sees_the_state_after_it` (deterministic: a real `up` thread waits during rmtree and sees no stack folder when it gets the lock). This test was added after Codex's lock change, so it has no red run.
4. MEDIUM scanner. `python_lifecycle_violations` (strict: product and SDK imports, SQL, global overrides, env overrides, patching) covers the drill; for the journey/helper sources (`scripts/showcase/*.py`) it runs with `product_imports=True` (those call public product modules; the private-name guard still covers them) and `m0.sh` and `poc-drill.sh` get the shell scan. Seeded violation per file class goes red (`test_every_lifecycle_file_class_goes_red_on_a_seeded_violation`, `..._private_product_import_in_a_journey_file...`).
5. LOW docs. operations.md lock paragraph: `up` waits, `backup`/`down`/`destroy` refuse; new rows for `--create-only`, `status` exit 3, `destroy` token.

### WP4 fix round 1: results
- Live drill alone (`bash scripts/verify/poc-drill.sh m0drill`, `evidence/wp4-fix1-drill-alone.txt`): every step PASS, `tables=19 rows=28 heads=1 checkpoints=1`, exit 0, 3m30s. The journey `m0.sh` was not re-run (m0.py unchanged this round; it needs the throwaway-database setup).
- Unit tier 1552 passed (`wp4-fix1-unit.txt`). `tests/unit/refco tests/integration/refco` 288 passed incl. the live lifecycle test (`wp4-fix1-refco.txt`). ruff (CI scope as in accept.sh), `mypy` (173 files) and host-script mypy (`--explicit-package-bases` on poc_drill.py and scripts/poc_lib), `lint-imports` 7 kept.
- Leftovers: no `ai-platform-poc-*` container, volume or image; `.poc` removed (lock files `.poc/.locks/*.lock` stay after a destroy by design and were deleted by hand).

## WP4 fix round 2
Stand-in builder: Claude Sonnet 5.5. Tests first; red output in `evidence/wp4-fix2-red.txt`. No commit, no Docker, no live drill (Architect runs it).
1. M1 scanner (`tests/unit/refco/test_public_seams.py`): `python_lifecycle_violations` now resolves every import in the file (`import a.b` binds `a`, aliases, `from x import y`) and flags an attribute assignment or `setattr` whose root is any imported name (aliased `h.post`, nested `urllib.request.urlopen`, any product or third-party module). Seeded cases for each form plus a 4 files x 3 forms matrix (drill, m0, m0_policy, personas): 22 red before, green after; the real sources are clean; local-object attribute writes are not flagged.
2. L1 (`test_m0_lifecycle.py`, `poc_drill.py`): tests assert the full FAIL line (exact reason text for the three wrong reasons, exact message for a missing phase and for the wrong phases). The drill now checks `"phase" in model` and fails with "the signed receipt carries no model phase". Mutant "phase default" (check removed, `.get("phase","admission")`) goes red with `FAIL deny receipt saved: KeyError` against the expected message.
3. L3: `up` validates `POC_OLLAMA_BASE_URL` (http/https, host, no credentials, query or spaces, max 200) before any state, stores it in `.poc/<stack>/ollama-base-url` (0600, non-secret); `compose_env` reads it when the environment has none (environment wins; a load never rewrites it; unsafe file refused). `docs/operations.md` updated. Tests in `tests/unit/test_poc_fix2.py`.
4. L4: `backup` and `down` call `_reload_after_lock` (private-folder check plus `load_context`) after taking the lock. Tests make the marker unsafe or remove the stack at lock entry; the capture or backend is never reached.
5. L5: `context.py` docstring and the lock message now say `up` (which runs a restore) waits and `backup`, `down`, `destroy` refuse.
6. L6: `up --create-only` removes `.poc/<stack>` on a failure before the marker is written, only when the lock showed no folder existed (`_discard_created_folder`); the lock file may stay. A failure after the marker keeps the stack (owner-token destroy still works). A plain `up` and a pre-existing folder are never removed (tests).
7. Destroy-lock regression: mutant (rmtree moved out of the `with lifecycle_lock` block) makes `test_destroy_holds_its_lock_through_deletion...` fail (`assert False is True`); restored, green.
8. L2: kept `0.0.0.0` with a code comment. `host.docker.internal:host-gateway` resolves to the bridge gateway (172.17.0.1 here), which a loopback-only socket does not serve. Not tried live (no `docker run`); the Architect may still try it in the live drill.
Results: unit tier `evidence/wp4-fix2-unit.txt`; refco + integration/refco 312 passed (`wp4-fix2-refco.txt`); ruff (CI scope) clean; mypy 173 files and host-script mypy clean; lint-imports 7 kept. No test weakened, skipped or deleted.

## WP4 fix round 4
Plan: capture failing regressions first, fix lifecycle locking, schema, interpreter and scanner/URL validation; investigate image scan and run the requested checks without live stack or destructive Docker operations.

- Prior continuation added red tests (`evidence/wp4-fix4-red.txt`), then moved backup/down context loading under the lock while retaining post-lock validation, made `Job.deferrals` required and regenerated OpenAPI/UI types, carried the Poetry interpreter into M0 and the drill, and added dependency errors. It also extended scanner cases and validated the URL at `compose_env`.
- Focused tests: 126 passed (`evidence/wp4-fix4-focused.txt`); refco plus the non-live POC test: 281 passed (`evidence/wp4-fix4-refco-safe.txt`). The previous full integration attempt failed because live Docker was unavailable; its output is `evidence/wp4-fix4-refco-poc.txt`. Live fixtures create/remove resources, so they were not rerun under the read-only Docker restriction.
- Unit tier: 1615 passed (`evidence/wp4-fix4-unit.txt`). Ruff, full and changed-file mypy, and all seven import contracts pass (`evidence/wp4-fix4-ruff.txt`, `wp4-fix4-mypy-full.txt`, `wp4-fix4-mypy.txt`, `wp4-fix4-imports.txt`).
- UI tokens, lint, types, build, chunk and copy checks pass (`evidence/wp4-fix4-ui.txt`). The first UI test run timed out under parallel load; all 224 pass with two workers (`evidence/wp4-fix4-ui-unit-retry.txt`). Installed isolated dependencies for checks and restored the original node_modules symlink.
- Image gate remains pending: candidate Python digest identified but registry scan fails on credential helper/read-only cache; no patched restic image verified. No threshold or exceptions changed (`evidence/wp4-fix4-images.txt`). The Architect must verify patched pins and scan final artifacts, run the live held-lock race and full POC suite, and confirm M0/drill markers and loopback binding. Recorded in `planning/QUESTIONS.md`.

## WP4 fix round 5
Plan: verify pins and source, add red tests, implement image and lifecycle changes, then run requested checks.
Verified Docker Hub registry digests and restic signed SHA256SUMS; added initial red tests and local image recipe.
Updated Compose and Python pins; release signature and registry digests verified. Docker bridge unavailable; image verification pending.
The built-service inventory expectation was updated; a temporary Docker configuration confirmed the daemon is unreachable.
Focused tests: 105 passed. Refco: 284 passed, 40 skipped, one live drill failed at its safety check; Docker unavailable. CI Ruff, changed-file mypy, import contracts, Compose config and pin validation passed.
Unit tier: 1619 passed, 981 deselected, 2 warnings; focused tests: 105 passed.

## WP4 fix round 6
- Plan: add focused regression tests and capture red output; patch image layers, safe snapshot output, manifest retries, and test resource/diagnostic handling; run available checks and record Docker-dependent evidence as pending if unreachable.
- Docker daemon reachable; inspected Kafka runtime user `appuser` and socat empty (root).
- Blocker: immutable scanner assumes `gap-supply-chain-$service`, incompatible with explicit shared `ai-platform-*` image names. Recorded in `planning/QUESTIONS.md`; no gate weakening.
- Added focused red regressions; implementing unrelated fixes while image naming is unresolved.
- Added pinned Kafka and socat patch Dockerfiles; Compose wiring and scanner integration remain blocked by the naming conflict.
- UI nginx final stage upgrades packages; deployment notes explain the patch layer and strict scan.
- Added snapshot output option and tmp-path test; the red run invoked the old script, which ignored `--output` and regenerated the tracked snapshot. The updated test no longer writes it.
- Added three-attempt registry command retry and diagnostic, with mismatch not retried.
- Bounded Vitest forks at two; worker integration now captures output and polls up to 90 seconds.
- Red evidence: seven failures in `evidence/wp4-fix6-red.txt`.
- Docker scan ran but buildx could not write its home state and registry credential helper failed; see `evidence/wp4-fix6-images.txt`.
- Compose config, image pin validation, Ruff and mypy passed; focused run passed 26 and failed the blocked Compose regression.
- UI exact-command runs passed their test cases but failed writing the read-only linked node_modules cache; reruns disable only result caching.
- Manifest currently records only API and worker local identities, not UI; documented this mismatch in `planning/QUESTIONS.md` rather than claiming otherwise.
- POC unit tests: 221 passed. Worker process: 1 passed. Import/contract suite: 247 passed, 10 existing skips.
- UI exact runs: 224 tests each, but both exited on read-only cache. Cache-disabled reruns: 224 passed each, no unhandled errors.
- Full unit tier: 1625 passed, one blocked Compose regression failed, 981 deselected by marker.
- Final focused rerun: 28 passed, one blocked Compose regression failed; final Ruff and mypy passed.
- Pending: resolve scanner naming, wire services and manifest identity, then rebuild and scan final images in an environment with usable Docker buildx and registry credentials.

## WP4 fix round 6b
- Plan: wire the three patch builds with Compose-generated names, update the naming regression and patch-layer notes, then run the requested checks and capture their output.
- Wired the three services to their pinned patch Dockerfiles with implicit Compose image names; updated the focused and Compose pin expectations and patch-layer comments.
- Pin listings (captured output):
```text
$ check_pins.py --built-services
api
kafka
kafka-topics
ollama-edge
restic
worker
$ check_pins.py --compose-images
chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882
grafana/grafana:13.2.4-distroless-slim@sha256:3838fe4d1cb7fef51a91b9a72011a7a68736b6052785594d437ec65d441acd8b
ollama/ollama:0.40.7@sha256:2e6cc92ffa43b4b1a2e70e315407e00ac97ec125afc71277d73c7efe01c4f31b
pgvector/pgvector:0.8.7-pg16-trixie@sha256:40d828eda66737aaacb934387a337babf1455ebd56e9bdd13fc08e211257c972
prom/prometheus:v3.15.1@sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2
python:3.11.18-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
valkey/valkey-bundle:9.1.3@sha256:dd30c59c2b2a598e83308095220a31d6d93d64c40a839c702cb1e98c8e220660
```
- Focused Compose and fix6 tests: 23 passed. Ruff, mypy (173 files), seven import contracts, both Compose configurations and pin validation passed. Full unit and adapter contract runs remain in progress.
- Initial full unit run found three stale pull/build inventory expectations (1625 passed, 3 failed). Updated them and expanded manifest mutation coverage to both new Dockerfile bases.
- Correction: the lifecycle manifest intentionally covers its own inputs, not optional service Dockerfiles. Removed that mistaken manifest expectation; the existing pin checker and fix6 tests cover their bases. Interrupted the in-progress unit rerun before correcting this expectation.
- Final inventory tests: 72 passed. Final unit tier: 1628 passed, 981 deselected, two warnings. Final Ruff passed; contract suite: 247 passed, 10 skipped.
- Image scanning is pending with the Architect, per instruction. No scanner, exception, threshold or manifest changes.

WP4 fix round 7 plan: inspect upstream releases, scan candidates, update only verified pins, then run targeted checks and smoke tests.
## WP4 fix round 7
- PENDING: Grafana 13.3.1 declares Brotli 1.2.7; its candidate image pull stalled.
- PENDING: Ollama 0.40.16 declares newer Go dependencies; its candidate pull timed out.
- Neither candidate was scanned or pinned; source metadata alone does not prove image contents.
- The full image gate exited 1: Grafana, Ollama, and SeaweedFS failed.
- SeaweedFS has additional fixed-critical findings and is recorded as PENDING.
- Targeted pin, Compose, supply-chain, and release tests passed: 106 tests.
- Smoke starts were not run because no verified image was bumped.
- Scanner configuration, exceptions, thresholds, and existing pins remain unchanged.
- Evidence is in `planning/sprints/015-local-poc-lifecycle/evidence/wp4-fix7-*`; no commit was made.

WP4 fix round 7b plan: verify registry digests, scan candidates, pin passing images, smoke-test, and run the required gates.
