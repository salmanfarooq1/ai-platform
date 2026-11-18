# Sprint 015: Builder brief

You build only the WP named in the Architect's launch, in
`/home/ubuntu/ai-platform-sprints/015-local-poc-lifecycle`, branch
`sprint/015-local-poc-lifecycle`. This pack supplies the owner-approved sprint
routing in place of the program's Luna default. Do not launch anything while
merely drafting/reviewing this pack.

## Read
`AGENTS.md`, MAP, DECISIONS, builder-method, conventions, ADR-0035, architecture
rules, then this pack's requirements, blueprint, test-spec and threat model.
Read the exact source paths for your WP below. Blueprint defines behavior;
test-spec defines exact names/assertions. Record conflicts in QUESTIONS and log.

## Launches, in order
| Launch | Builder | Independent reviewer | M0 step |
|---|---|---|---|
| WP0 | `gpt-6.1-terra` | `gpt-6.1-sol` | Explicit deny before inference |
| WP1 | `gpt-6.1-terra` | `gpt-6.1-sol` | One-command default up |
| WP2 | `gpt-6.1-sol` | `gpt-6.1-terra` | Persistent signed receipt identity |
| WP3 | `gpt-6.1-sol` | `gpt-6.1-terra` | Checked backup/down/up |
| WP4 | `gpt-6.1-terra` | `gpt-6.1-sol` | Real complete restore journey |

One owner go-ahead covers the sprint; it was given 2026-11-17. The Architect
launches each WP. One WP per call. WP3 may use separate backup and teardown
launches under the same routing, each with its own cross-model review. The reviewer independently reads the diff, checks test
integrity, reruns checks and returns exact findings. Fix with the same builder;
review again before the next launch. Reports are about 20 lines.

## WP0
Read: `scripts/e2e/serve.py`, `scripts/showcase/m0.py`, policy restore helper,
`ui/playwright.config.ts`, `ui/e2e/showcase-m0.spec.ts`, `api/services/llm.py`,
`api/services/model_calls.py`, `tests/unit/test_llm.py`.
1. Write every WP0 test in test-spec; capture red results before changes.
2. Seed an allowed baseline. Publish explicit alias deny via the existing journey
   helper and public policy seam; preserve concurrent updates on restore.
3. Resolve Poetry from environment for both configurations. Require governed caller
   and context in both legacy functions; preserve semantic regression assertions.
Tests/commands: `poetry run pytest -q tests/unit/test_llm.py tests/unit/test_playwright_config.py tests/integration/refco tests/integration/test_llm_governance.py`;
`npm --prefix ui run build`; `npm --prefix ui run test:e2e -- --project=showcase-m0`.
Allowed: the read paths, an operator helper under `scripts/showcase/`, exact WP0
named test files, regression test setup and pack log/evidence. Done: WP0 tests and
browser pass; no permanent seed deny or ungoverned provider path remains.

## WP1
Read: `docker-compose.yml`, `Dockerfile`, `scripts/setup_db.sh`,
`scripts/supply_chain/check_pins.py`, `scripts/supply_chain/image_scan.sh`.
1. Write every WP1 test; record red results.
2. Add API, shared artifact, hardening for both services and fresh-db bootstrap.
3. Build/verify release manifest and index proofs across every optional profile;
   keep local output identity distinct. Register artifacts in existing scan gates.
Tests/commands: `poetry run pytest -q tests/unit/test_poc_compose.py tests/unit/test_release_manifest.py tests/integration/poc/test_up.py`;
`poetry run python scripts/supply_chain/check_pins.py`.
Allowed: read paths, `scripts/release/build_manifest.py`, `scripts/poc`,
`scripts/poc_lib/` (up/Runner only), `docker/` bootstrap helper, named WP1 tests,
log/evidence. Done: single up starts exactly four healthy services, no manual
setup, pins verified and resource usage captured. Key tests complete after WP2.

## WP2
Read: `evidence/receipts.py`, `core/settings.py`, `workers/handlers/purge.py`,
`docker-compose.yml`, `.gitignore`, `.dockerignore`.
1. Write every WP2 test; record red results.
2. Implement private file lifecycle and validated file-backed settings, mount the
   same key into API/worker; preserve it through down. Reject unsafe files.
3. Add exact previous-public-key restore validation and operator key-backup guidance.
Tests/commands: `poetry run pytest -q tests/unit/test_poc_keys.py tests/unit/test_settings.py tests/integration/poc/test_keys.py tests/integration/poc/test_restore.py::test_wrong_key_id_requires_previous_public_key`.
Allowed: read paths, `scripts/poc_lib/` (keys), `scripts/poc_backup/` (key validation),
exact WP2 tests, generated settings docs and operator runbook, log/evidence.
Done: persistent key tests pass and secret sentinel checks expose no material.

## WP3
Read: blueprint WP3, purge handler, `adapters/local_object_store.py`,
`core/database/jobs.py`, `adapters/pg_outbox_events.py`, existing public admin seams.
1. Write every WP3 test; record red results. First complete the Runner/manifest
   contract, then online dump/object capture and shared purge lock.
2. Add a pinned restic profile, one staged snapshot and validation against scratch DB.
3. Implement down preflights in exact order; restore before reporting healthy;
   report Valkey losses and restore same-day cost counters before health.
Tests/commands: `poetry run pytest -q tests/unit/test_poc.py tests/unit/test_poc_backup.py tests/integration/poc`.
Allowed: `scripts/poc`, `scripts/poc_lib/`, `scripts/poc_backup/`,
`docker/poc.override.yml`, `tests/unit/test_poc_compose.py`,
`workers/handlers/purge.py`, `core/database/` (shared lock/public recovery seam),
`docker-compose.yml` (backup service), exact WP3 tests, general budget-recovery
product code with named regression tests, operator docs and log/evidence.
If schema work is needed, assign next free forward migration with RLS/GRANT tests;
never add maintenance state. Done: WP3 negatives pass, actual restic/scratch restore
pass and unsafe down cannot remove anything. No unverified shell/tool assumptions.

## WP4
Read: `scripts/showcase/m0.sh`, `m0.py`, `scripts/verify/receipt.py`, public `poc`
commands, WP0 policy helper and `test-spec.md` WP4.
1. Write WP4 tests before implementation and capture failures.
2. Add required `scripts/verify/poc-drill.sh <stack>`; complete the M0 entry path,
   compare snapshot counts/heads, verify saved receipts offline, make a new call.
3. Run full `accept.sh`; update product docs, MAP, CHANGELOG and sprint report.
Tests/commands: `poetry run pytest -q tests/unit/refco tests/integration/refco`;
`bash planning/sprints/015-local-poc-lifecycle/accept.sh`.
Allowed: `scripts/showcase/`, `scripts/verify/poc-drill.sh`, exact WP4 tests,
operator docs, planning status, CHANGELOG, pack report/log/evidence.
Done: real drill and browser pass with no required SKIP; every acceptance item
has command output and cross-review findings are closed.

## Launch form
The Architect runs the selected builder after readiness checks. Example for WP2:
```bash
codex exec -C /home/ubuntu/ai-platform-sprints/015-local-poc-lifecycle -m gpt-6.1-sol -c model_reasoning_effort=high -s workspace-write --json -o /tmp/015-wp2-last.txt 'Read planning/sprints/015-local-poc-lifecycle/builder-brief.md and do WP2 only.' < /dev/null
```
Use the table's other model for a separate read/review call after each launch;
review has no implementation authority. Never substitute models silently.

## Checks and hard rules
Use prepared Poetry 2.3.3, Node 24 and installed browsers on PATH; no tool installs,
no `playwright install`, no `.env` edits. Run package commands plus ruff, mypy and
import contracts after each WP. Architect runs real Docker/browser/drill checks
when builder sandbox cannot. Missing capability is pending evidence, never PASS.
No commit, push, stash, reset, branch change or test weakening. No secrets in argv,
environment exports, logs, evidence or data backups. Rule 10: public showcase seams
only; fix a general product gap with tests. No optional profile on default up.
Only fixture-owned runtime data may be destroyed by the drill; fully tear down its
stack afterward. Never touch existing owner or developer volumes. Preserve keys, passwords and repositories. Follow AGENTS stop conditions
on affected work and continue unaffected work. No money or hosted inference.

## Finish each launch
Append files, red/green commands, captured results, assertion changes, findings
and remaining questions to build-log. Report about 20 lines: outcome, acceptance
items, test delta, actual evidence paths, risks and proposed human commit commands.
Only the owner commits, pushes and creates `v0.15.0` after final acceptance.
