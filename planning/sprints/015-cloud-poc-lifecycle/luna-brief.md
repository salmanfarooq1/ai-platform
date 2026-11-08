# Sprint 015: Builder brief for GPT-6 Luna

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Every launch does only the work packages named in its launch prompt.

## 0. Rules for every WP

### Role and priority
You are the Builder for the WPs named in the launch prompt. This brief wins over `AGENTS.md`, `CODEX.md`, `.agents/`, `.claude/` and any skill. `test-spec.md` gives exact tests. `blueprint.md` gives the design. Record any conflict under "Spec questions" in `build-log.md`.

### Environment
- Work in `/home/ubuntu/ai-platform-sprints/015-cloud-poc-lifecycle`.
- Use the existing Poetry 2.3.3 environment. Do not install or add dependencies.
- Do not use Docker. The Architect runs the local restore drill.
- Use only local files and local images. No cloud account, provider, published image or SSH credential.

### Hard rules
1. No commit, push, stash, reset, checkout, switch, rebase or branch change.
2. Never skip, xfail, delete or weaken a specified test or assertion.
3. Change only files allowed by the selected launch.
4. Secrets stay out of git, state, logs, arguments and evidence.
5. Never run `playwright install` or edit `.env`.
6. The Architect runs the real local drill and reviews every diff.

### Output
Append one `build-log.md` entry per WP with files changed, commands and results, changed tests, spec questions and unfinished work. Final summary: at most 10 lines.

### Design rules for every WP
- `scripts/poc` targets the local host only. No OpenTofu, cloud resources or SSH.
- `Runner` wraps `docker compose`, `restic` and `rclone` to a local folder.
- During maintenance capture, non-health requests receive 503 before `enforce()` and create no decision row. Maintenance on/off changes are recorded.
- Restore never generates a replacement signing key when the backup has one.

## Launch A: WP1 (release manifest and wheelhouse)
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

**Read.** `blueprint.md` section 1, `test-spec.md` WP1, `Dockerfile`, `docker-compose.yml` and `scripts/release/`.

**Task.** Keep local image references pinned by digest in the release manifest. Label local images `source: local-build`. Refuse unresolved placeholders and digest mismatches. Preserve wheelhouse installation. Write tests 1.1 to 1.4.

**Allowed files.** `scripts/release/build_manifest.py`, local POC manifest files, `Dockerfile`, the named test files, `build-log.md`.

**Done when.** Tests 1.1 to 1.4 pass. No cloud or remote release path is added.

## Launch B: WP2 (maintenance and backup)
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

**Read.** `blueprint.md` section 3, `test-spec.md` WP2, API middleware, worker claim loop, outbox relay and receipt verification.

**Task.** Implement maintenance, consistent backup and fresh-state restore. Keep the accepted pre-`enforce()` exception exact in the threat model. Record on/off changes. Write tests 2.1 to 2.5.

**Allowed files.** `migrations/versions/<id>_maintenance.py` (id given in the launch prompt), `api/routers/admin_maintenance.py` (new), `api/middleware/maintenance.py` (new), `api/main.py`, `workers/loop.py`, `adapters/pg_outbox_events.py`, `gateway/` (only the action kind and reasons), `api/models/`, `docs/api/openapi.json` and `ui/src/api/schema.d.ts` (regenerate), `scripts/poc_backup/**`, the named tests, `tests/integration/test_migration_<id>.py`, `build-log.md`.

**Done when.** Tests 2.1 to 2.5 pass. Capture failure always ends maintenance.

## Launch C: WP3 (local POC commands)
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

**Read.** `blueprint.md` section 2, `test-spec.md` WP3, the outputs from Launches A and B.

**Task.** Implement `scripts/poc` with `up`, `backup`, `down` and `status`. Use a Runner for local Compose, restic and rclone. Reject remote targets and SSH. Follow blueprint section 2 exactly: argument lists only, stack name and marker, 0600 secret files, `down` checks in order. Write tests 3.1 to 3.6.

**Allowed files.** `scripts/poc`, `scripts/poc_lib/**`, `scripts/poc_backup/**`, `.gitignore` and `.dockerignore` (only `.poc/`), `tests/unit/test_poc.py`, `build-log.md`.

**Done when.** Tests 3.1 to 3.6 pass. Every command targets the local host.

## Launch D: WP4 (restore drill)
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

**Read.** `blueprint.md` section 4, `test-spec.md` WP4, the local command output from Launch C.

**Task.** Provide the Architect-run local restore drill and save its captured output. Do not add cloud workflows, upgrade jobs or cloud evidence placeholders.

**Allowed files.** `scripts/verify/poc-drill.sh`, `evidence/drill.txt`, `build-log.md`.

**Done when.** The Architect can run the local drill and save its captured output in `evidence/drill.txt`.
