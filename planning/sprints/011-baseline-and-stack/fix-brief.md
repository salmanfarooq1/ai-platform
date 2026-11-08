# Sprint 011: Fix brief (round 2)

You are the Builder. Work in `/home/ubuntu/ai-platform` on the current branch, `sprint/011-baseline-and-stack`. Read `qa-independent.md` in this folder first. Fix only the items below. Make each change as small as you can.

## Hard rules
- Do not commit, push, merge, stash, reset or switch branches. Do not delete any file you did not create, except the three recipe folders named in F5.
- Do not weaken, skip or delete a test. Do not add a pytest skip.
- Do not touch untracked root files you did not create: `"# Blueprint YAML Reference"`, `deployment_sprint_plan.md`, `fronted_master_plan.md`, `project_finalization_plan.md`, `skills-lock.json`, `scripts/test_sample_search.py`, `.claude/skills/*`.
- No secrets in files or logs. Never run `playwright install`.
- If something blocks you, write it in `build-log.md` under "Round 2", skip only that item and continue.

## Items
**F1. CI scope.** In `.github/workflows/tests.yml`, lint, typecheck and the unit tier always run, for every change. The change scope may gate only the integration/e2e tier, the migration check and the image scan. In `scripts/ci/change_scope.py`, a `ui/` path also sets backend=true (`ui/nginx.conf` and `ui/vite.config.ts` are guarded by backend tests), and use `git diff --name-only --no-renames`. Update `tests/unit/test_ci_env.py` so that `["ui/src/app.tsx"]` gives `(True, True)`. Add a test that the lint, typecheck and unit jobs have no `if:` that reads the change scope.

**F2. PSF-2.0.** Remove `PSF-2.0` from `scripts/supply_chain/osi-licences.txt`. Keep the `aiohappyeyeballs|2.6.1|PSF-2.0` line in `licence-exceptions.txt`, and make sure the gate accepts an exception whose id is not on the OSI list only when the exact name and version match. Add `tests/fixtures/licence/spdx-osi.txt`: the OSI-approved SPDX ids, taken from https://spdx.org/licenses/licenses.json (`isOsiApproved: true`), with the list version and date on the first comment line. Add a unit test that every id in `osi-licences.txt` is in that fixture. The licence gate must still pass on the real tree and fail on `tests/fixtures/licence/non_osi`.

**F3. UI image.** Pin both `FROM` lines in `ui/Dockerfile.ui` to an exact tag plus `@sha256:` digest (Node 22 Alpine and nginx stable Alpine). Each release must be at least 14 days old today; get the digest and date from the Docker Hub tags API and record both in `evidence/pins.txt`. Make `scripts/supply_chain/check_pins.py` include `ui/Dockerfile.ui` (any `Dockerfile*` in the repo outside `node_modules`). Make `scripts/supply_chain/image_scan.sh` build and scan `ui/Dockerfile.ui`. Add a test that the pin checker rejects an unpinned `ui/Dockerfile.ui`.

**F4. Old volumes.** In `scripts/preflight.sh`, print a clear warning, not an error, when the volume `<project>_pgdata` exists and `<project>_pgdata_trixie` does not. Do the same for any other renamed volume in `docker-compose.yml`. Use the same project name logic the script already has. In `docs/postgres-upgrade.md`, add runnable commands, one per line: dump from the old volume with a temporary `pgvector/pgvector:pg16` container, then restore into the new stack with `pg_restore` or `psql`. Add a test for the warning with a stubbed engine, in the style of `tests/unit/test_preflight.py`.

**F5. Upstream images for optional profiles.** For `kafka`, `kafka-topics`, `seaweedfs`, `seaweedfs-init`, `ollama` and `ollama-pull` in `docker-compose.yml`, replace `build:` with `image:`, using the exact upstream reference already on the final `FROM` line of each recipe:
- `apache/kafka:4.3.1@sha256:77e3df90…` (copy it in full)
- `chrislusf/seaweedfs:4.47@sha256:ce9e796f…`
- `ollama/ollama:0.40.7@sha256:2e6cc92f…`

If the SeaweedFS recipe copies `docker/seaweedfs/s3.json`, mount it read-only through compose instead, and keep `s3.json`. Keep every other setting of those services the same: ports, healthchecks, users, env and volumes. Then delete `docker/kafka/` and `docker/ollama/`, and `docker/seaweedfs/` except `s3.json`. Remove the code paths, tests and docs that exist only for those recipes (for example the security build tests and `--built-services` for those services). Leave `--built-services` working for `worker` and the app image.

Then add `scripts/supply_chain/image-exceptions.txt` with this format: `image-ref|CVE|package|profile|expires YYYY-MM-DD|reason`. In `image_scan.sh`:
- An image used only by the `streams`, `lake` or `models` profiles is scanned with a generated grype config. That config ignores only its own unexpired exception lines.
- An expired line fails the gate.
- A line for an image used in the default set or in `observability` fails the gate.
- Every other image keeps the current rule: fail on a fixed critical.

Add unit tests for these four cases, using fixture files, not Docker. Start the exceptions file with a comment only. The lines come from the live scan in round 2b.

**F6. Small fixes.**
- `scripts/setup_db.sh`: use `POSTGRES_PASSWORD` (default `postgres`) in `MIGRATION_DATABASE_URL`. Fix the "postgres redis" text in `scripts/setup_db.sh`, `scripts/verify/observability.sh` and `scripts/verify/openshell.sh`. Fix the Redpanda mention in ADR-0008.
- `api/mcp/tools.py` and `api/mcp/resources.py`: on an unexpected exception, log one warning with the tool or resource name and `type(exc).__name__`, never the message. Extend the existing sentinel-secret test to assert the sentinel is not in the logs.
- `tests/unit/test_config_mode.py`: stop `LOG_LEVEL` from leaking into `os.environ` (use `monkeypatch.delenv(..., raising=False)` or restore it).
- `docker-compose.yml`: set `KAFKA_AUTO_CREATE_TOPICS_ENABLE` to `"false"`, and check that `scripts/verify/kafka.sh` still creates its topics first.
- `scripts/preflight.sh`: when `COMPOSE_PROFILES` is set, also check that profile's published ports (streams 19092, lake 8333, models 11434, observability 9090 and 3000). Read them from `docker compose config` if that is simple; otherwise use a fixed map.
- Pin exact versions for `license-checker` and `@cyclonedx/cyclonedx-npm` wherever `npm exec`/`npx` runs them.

## Checks (round 2a, no Docker needed)
Run these and save the output to `evidence/round2-<name>.txt`:
```bash
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/docs scripts/supply_chain scripts/ci
poetry run mypy
poetry run pytest -m unit -q -p no:cacheprovider
scripts/supply_chain/licence_gate.sh
scripts/supply_chain/licence_gate.sh --fixture tests/fixtures/licence/non_osi
poetry run python scripts/supply_chain/check_pins.py
```
Unit failures caused only by a missing Docker CLI are allowed; list them by name.

## Finish
Append a "Round 2" section to `build-log.md`: one line per item (done, or blocked with the reason) and the check results. Then stop and print a summary of at most 10 lines.
