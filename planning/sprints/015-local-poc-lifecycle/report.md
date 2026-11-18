# Sprint 015 pack rewrite report

Renamed the pack on disk to `015-local-poc-lifecycle`; all old-slug references removed.
Rewrote requirements, blueprint, acceptance, test-spec and threat-model.
Added executable accept.sh with baseline/final modes and per-check evidence logs.
Replaced luna-brief with builder-brief; rewrote readiness and build-log.
Updated MAP, sprint-map, conventions, DECISIONS and QUESTIONS.
WP0–WP4 each name their M0 step; Sol owns WP2/WP3, Terra WP0/WP1/WP4.
Each implementation launch requires independent review by the other model.
Specified 36 pytest nodes, one browser test and one real shell drill; negatives are explicit.
All 24 threat-model pytest references match test-spec exactly.
Open: explicit backup-age threshold; safe fixture-volume ownership within the one-project rule.
Code contradicts the brief's worker-hardening premise: worker is not yet hardened.
Compose lacks API; local app builds have image IDs, not multi-arch index identities.
The drill SKIP is in m0.py behind m0.sh; the pack targets the actual entry path.
Settings lacks file-backed keys; purge lacks a backup lock; Valkey has no durable job queue.
Seed denies all models, Poetry paths are fixed, and legacy generation bypasses governance.
Draft checks passed: shell/Python syntax, exact names, MAP limits, slug and scope checks.
Product acceptance was not run; no product/test/Compose changes, installs, commits or launches.
`git mv` failed on the read-only linked index; owner stages the filesystem rename.
Proposed owner commands: `git add -A -- planning`; `git commit -m "docs(planning): define local poc lifecycle pack"`.

## WP0 builder handoff
- Added explicit deny and compare-and-swap restore for the browser journey, leaving the seed baseline allowed.
- Required ModelCaller and enforcement context for both citation functions; migrated fake eval and regression setup.
- Poetry resolution uses PATH or POETRY, including paths containing spaces.
- The settings default assertion now isolates DEPLOY_SHAPE and env files; it still asserts single_tenant.
- Red evidence: wp0-settings-red.txt, wp0-red.txt and wp0-other-red.txt. Browser red was not a clean pre-change run; see build-log.
- Package: 74 passed; focused unit/network: 42 passed; settings mixed tier: 1 passed.
- Offline eval, UI build, mypy and import contracts passed; scoped ruff passed. Whole-tree ruff noted an unrelated concurrent WP2 lint issue.
- The removed 35-second retry fallback is replaced by ModelCaller's bounded 0.25-second first retry, with attempt/error checks retained.
- Manual real-provider eval requires a real governed context and paid verification, recorded in QUESTIONS.
- Live seed and alias checks pass (`wp0-seed.txt`, `wp0-alias.txt`); browser stalled after migration and was interrupted (`wp0-browser.txt`), so browser and independent review remain pending.
- Proposed human commit after review, with scope reviewed against concurrent work: `git add api/services/llm.py scripts/e2e/serve.py scripts/eval/suite.py scripts/showcase/m0_policy.py tests/integration/refco/test_m0.py tests/integration/refco/test_m0_restore.py tests/integration/test_llm_governance.py tests/unit/test_llm.py tests/unit/test_network_guard.py tests/unit/test_playwright_config.py tests/unit/test_settings_modules.py ui/e2e/showcase-m0.spec.ts ui/playwright.config.ts planning/QUESTIONS.md planning/sprints/015-local-poc-lifecycle` then `git commit -m "fix(gateway): require governed citation generation"`.

## WP2 builder report
WP2 only: private receipt identity and recovery-key validation implemented.
Followed pre-start-review and the owner's approved launch; existing planning/WP0 edits preserved.
Tests written before code; red evidence: `evidence/wp2-red.txt` (17 failed, 27 passed).
Exact WP2 command now: 45 passed, zero skips (`evidence/wp2-green.txt`, `wp2.xml`).
Full unit tier: 1241 passed (`evidence/wp2-unit.txt`, `wp2-unit.xml`).
Baseline unit: 1214 passed, 24 failed; concurrent WP0 added two more tests, so aggregate delta is shared.
Exclusive atomic creation, no-follow paths, ownership/mode/type checks, and concurrent-up locking added.
0600 host key/password in 0700 directories stay outside runtime volumes; restore never creates missing secrets.
Settings loads RECEIPT_SIGNING_KEY_FILE privately; inline/file conflicts fail; inline/previous keys still work.
Restore requires exact public bytes and derived id; no missing active private file or fabricated id is accepted.
Compose render and real Docker key-reader fixtures pass: both processes load one read-only-mounted key across recreation.
Real Postgres/API/worker tests pass across lifespan restart; saved receipts verify using saved trusted public keys.
Sentinel checks cover environment, subprocesses, Compose, repr/serialization, logs/stdout/stderr and public payloads.
All 25 existing Settings tests/39 assertions retained; no WP2 skip/xfail or weakened regression.
Full mypy (172 files), helper mypy (6 files), seven import contracts, full lint and generated docs checks pass.
Operator runbook documents separate protected offline key/password backup; .poc is ignored by git and Docker.
Pending A2: WP1 runner must merge the key fragment; WP3 must preserve secrets and invoke recovery checks.
Real container/down/up/snapshot/browser acceptance and independent cross-model review remain pending, never PASS.
No commits, pushes, stashes or .env edits; acceptance boxes remain open; MAP/CHANGELOG closure is WP4.
Proposed human staging/commit commands (review shared files before staging):
```bash
git add -- .gitignore .dockerignore core/settings.py evidence/receipts.py scripts/poc_lib/__init__.py scripts/poc_lib/keys.py scripts/poc_backup/__init__.py scripts/poc_backup/keys.py tests/unit/test_poc_keys.py tests/unit/test_settings.py tests/integration/poc/test_keys.py tests/integration/poc/test_restore.py docs/configuration.md docs/operations.md
git commit -m "feat(core): persist local poc receipt signing identity"
```
Stage this report, the WP2 log entries and WP2 evidence separately after reconciling concurrent sprint work.

## WP0 fix round 1
- Journal deletion and restore success now follow the admin transaction commit.
- All four Playwright Python servers use the resolved Poetry executable.
- Startup test runs reference-company startup and inspects the policy head and history.
- Failure test exercises the journey and verifies restoration or concurrent-head preservation.
- Adapter unknown-price fallback and governed unknown-alias denial are separate regressions.
- Current-code red: `evidence/wp0-fix1-red.txt` (journal and Poetry, 2 failed).
- Coverage-only findings already had correct production behavior; mutation reds show sensitivity:
  `wp0-fix1-startup-mutation-red.txt`, `wp0-fix1-flow-mutation-red.txt`,
  `wp0-fix1-pricing-mutation-red.txt`, `wp0-fix1-alias-mutation-red.txt`.
- Focused green: `wp0-fix1-green-initial.txt`, `wp0-fix1-flow-first.txt`.
- Unit/import checks: `wp0-fix1-unit.txt` (91 passed); scoped Ruff, mypy and UI build passed.
- Browser journey and cleanup evidence remain pending: Architect runs it after WP2.
- WP0 is not accepted until browser evidence and independent review complete.
- No commit, push, stash or browser run; WP2 files excluded.
- Proposed human commit: review the existing WP0 staging command above and include these fix-round tests and evidence before `git commit -m "fix(gateway): require governed citation generation"`.

## WP4 fix round 6
- Partial; do not accept the image gate. The immutable scanner tags each built service `gap-supply-chain-$service`, incompatible with the requested shared explicitly named `ai-platform-*` images. Decision recorded in `planning/QUESTIONS.md`.
- Added pinned socat/Kafka patch Dockerfiles, not wired to Compose; nginx patch layer is active.
- Snapshot updates support `--output`; the test uses a temporary file. The first red run used the old script and regenerated the tracked snapshot despite its argument.
- Registry lookups retry command errors; digest verification remains strict. Vitest forks are bounded; worker startup output is captured.
- Docker was reachable but the image scan failed: read-only buildx state and credential helper errors. Evidence: `evidence/wp4-fix6-images.txt`.
- The focused run has 26 passes and one expected failure for blocked Compose wiring. No gate was changed.
- Human: resolve the scanner interface conflict, complete the Compose integration and rerun all acceptance evidence before staging.
- Proposed human commit after resolving the blocker: `git add <reviewed WP4 fix6 files> && git commit -m "fix(ops): patch and verify local service images"`.
- Final focused: 28 passed, one blocked Compose failure. Full unit: 1625 passed, one failure, 981 marker deselections. POC: 221 passed; worker: 1 passed; contracts/imports: 247 passed, 10 existing skips.
- Ruff, mypy, Compose config and pin validation passed. UI: both exact runs completed 224 tests but failed on the read-only shared cache; two cache-disabled runs passed 224 each.
- UI image identity is not currently included in the release manifest; see `planning/QUESTIONS.md`.

## WP4 fix round 6b
- DONE: Compose builds ollama-edge, kafka and kafka-topics with implicit per-service image names.
- DONE: Both Kafka services use the same build context; other service settings are retained.
- DONE: Patch Dockerfiles retain pinned bases and runtime users; comments point to the patch-layer guidance.
- DONE: UI patch comment corrected; no manifest change.
- DONE: Architect decision resolves the fix6 question.
- DONE: Pin validation and both Compose configuration checks passed; listings are in the build log.
- DONE: Focused Compose/fix6 tests: 23 passed; inventory tests: 72 passed.
- DONE: Unit tier: 1628 passed, 981 deselected; contracts/import tests: 247 passed, 10 skipped.
- DONE: Ruff, mypy (173 files) and seven import contracts passed.
- PENDING: Architect runs the unchanged image scan outside the sandbox.
- Evidence: `evidence/wp4-fix6b-*.txt`; the initial unit run records three stale expectations, fixed in the final run.
- No scanner, exception, threshold or manifest changes; no commit or push.
- Proposed human commit: `git add <reviewed WP4 fix files> && git commit -m "fix(ops): wire patched service images"`.

## WP4 fix round 7
- Candidate image verification is pending; see `planning/QUESTIONS.md` and `evidence/wp4-fix7-*`. No image pins were changed.
- Proposed human commit after review: `git add planning/QUESTIONS.md planning/sprints/015-local-poc-lifecycle && git commit -m "docs(ops): record image scan blockers"`.

## Sprint close (2026-11-19, Architect)
- Last full `accept.sh` (2026-11-18 17:50): 24 of 25 checks pass, including unit, all tiers, Playwright, live M0 journey and the restore drill. Only `image-scan` fails.
- Since then: fix7/7b pinned Grafana 13.3.1-distroless-slim by digest (Grype clean, rc=0) and recorded the Ollama and SeaweedFS findings. Quick non-Docker re-check: see `scratch/015/runs/quick-*.log` result in the close message.
- **Deferred by owner decision S015-image-defer:** Ollama 0.40.7 -> 0.40.16 and SeaweedFS 4.47 -> 4.54, pull + Grype scan + digest pin. First item of Sprint 016. Gate not lowered, no exception.
- Lost time: slow registry pulls (34 KB/s), a DNS outage, Docker Desktop stuck stopping, and two WSL restarts that killed builder runs. The Docker/WSL systemd race is fixed (`systemd=false`).
- Commit is done by the owner.

