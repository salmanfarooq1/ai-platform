# Sprint 015: Local POC lifecycle. Blueprint

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

## 1. Local release bundle
- `scripts/release/build_manifest.py` records image references pinned by digest. `poc up` refuses unresolved placeholders or a digest mismatch.
- The local bundle uses local image ids and labels the manifest `source: local-build`.
- The app image installs Python dependencies from its wheelhouse with `pip install --no-index --find-links`.

## 2. Local POC command
`scripts/poc` offers `up`, `backup`, `down` and `status`. It targets the local host only. A `Runner` wraps `docker compose`, `restic` and `rclone` to a local folder, so tests use fakes. No OpenTofu or SSH is used.
- `scripts/poc` is Python. Every subprocess call is an argument list: no `shell=True`, no `os.system`, no string commands.
- Every command needs a stack name matching `^[a-z][a-z0-9-]{2,30}$`. There is no default stack. A stack marker (`.poc/<stack>/marker.json`, git- and docker-ignored) names the compose project and volumes the stack owns; a marker that does not match refuses every command.
- Secrets (restic password, recovery reference) never go into git, logs, command arguments or evidence. They live in 0600 files and are passed by reference.
- `down` runs only after every check passes, in this order: the marker matches; the recovery reference `POC_RECOVERY_REF` resolves; the latest backup is newer than the last decision write and its manifest restores in a test restore. Then it removes only the containers and volumes the marker names, and prints what it removed.

## 3. Maintenance, backup and restore
- Maintenance state is one row in Postgres (new migration with upgrade, downgrade and a migration test; the Architect assigns the id at launch), so the API, every worker and the relay read the same state. Each process reads it at most once per second (cached), and always at the start of a job claim and a relay batch.
- `POST /v1/admin/maintenance` (`admin` scope) takes `{"on": bool, "max_seconds": int}` (1 to 3600, default 900). Each change is a recorded decision. Maintenance ends by itself after `max_seconds`.
- A middleware answers 503 with code `maintenance` and a `Retry-After` header to every request except `GET /health`, `GET /v1/health` and the maintenance endpoint. This happens before `enforce()`, so these 503s write no decision row while the database is captured. That is an accepted, documented exception (threat model and `conventions.md`).
- Workers claim nothing and the relay publishes nothing. Capture waits for active work to finish, bounded at 60 seconds.
- One backup manifest binds the schema head, database dumps, object hashes, signing-key ids, row counts and tenant chain heads. Store the backup through restic with rclone to a local folder.
- Restore into fresh local state. Verify object hashes, row counts, chain continuity, old receipt signatures and a smoke search before switching over. Never generate a new signing key when the backup contains one.
- Any capture error ends maintenance and marks the backup failed.

## 4. Restore drill
The Architect runs the drill script on this machine. It brings up the local stack, seeds the fixture, runs a search, backs up, stops the stack, brings it up again and verifies restored rows, chain heads, an old receipt and the signing-key id. Save captured output as evidence.

## 5. Out of scope
OpenTofu, cloud resources, remote Compose, Caddy, SSH, cloud workflows and previous-release upgrades belong to the cloud track, Sprint 031 at the latest.
