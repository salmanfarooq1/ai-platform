# Sprint 015: Blueprint

## WP0 — explicit governed journey
M0: deny before inference. `serve.py --reference-company` leaves the baseline
allowed. Browser setup invokes the same `publish_journey_policy` path as M0 via a
local operator helper, never a special HTTP bypass. Preserve every baseline field,
exclude only the journey alias, and restore as a new version only if its head is
still current. Cleanup runs on assertion failure and signals. Resolve Poetry by
`POETRY` executable override or PATH, with safe argument handling.
`generate_with_citations` and `generate_with_routing` require `ModelCaller` and
`EnforcementContext`; reject explicit None and omitted arguments before provider
work. Retain citation, usage and error assertions through the governed path;
retain retry counts/errors through ModelCaller, which owns bounded retries.
Correct the old bypass-specific sleep expectation explicitly in the report.

## WP1 — compose and release identity
M0: one-command up. Add default `api` using the worker's app image and Dockerfile;
apply `read_only`, `cap_drop: [ALL]`, `no-new-privileges` and healthchecks to both.
Give only explicit object mounts and tmpfs paths write access. Bind API to loopback.
`up` initializes app credentials and migrates as owner before starting API/worker
as `gap_app`; fresh volumes require no manual `setup_db.sh`. No optional profile
is inherited from ambient `COMPOSE_PROFILES`.
`scripts/release/build_manifest.py` checks all profiles and Dockerfile FROM inputs,
rejects floating refs, placeholders and child manifests, and verifies index metadata
and selected platform identity. Record the source, Compose digest, external indexes,
local app immutable output ID and pinned build inputs. Verify manifest/artifacts
before starting. A local app build is labelled `source: local-build`, never given
a fictitious index digest. Capture registry index proof when resolving pins; an
unverifiable pin fails. Keep existing supply-chain scans; add API and restic coverage.

## WP2 — secret lifecycle
M0: stable receipt identity. Create private 0700 `.poc/<stack>/` and 0600 key and
repository-password files atomically with exclusive/no-follow semantics. Refuse
symlinks, foreign ownership, unsafe modes, malformed keys and ambiguous key sources.
Extend validated Settings with `RECEIPT_SIGNING_KEY_FILE`; load at startup without
copying secret bytes into environment, argv or logs. Inline key remains supported
for existing deployments; configuring both sources fails. API and worker mount the
same file under `/run/secrets/`; purge checkpoints must share the receipt key.
`down` preserves these host files and backups. A restore never creates a missing
key silently. Match key id AND raw public bytes; rotation is allowed only when the
backup public key is explicitly in `receipt_previous_public_keys` and its id agrees.
Runbook: operator copies the private key separately to protected offline storage,
keeps mode 0600 and verifies its derived public id on recovery; never include it
or the restic password in the data snapshot, build context or evidence.

## WP3 — backup, validation and safe teardown
M0: backup/down/up. `scripts/poc {up,backup,down,status} <stack>` is a local operator
CLI. `status --json` exposes non-secret recovery checks and loss warnings. Use a
fakeable Runner with argument arrays, no shell interpolation. Reject remote Docker
contexts. Validate `^[a-z][a-z0-9-]{2,30}$` before any tool or path operation.
A private marker binds stack, project, database and exact owned volume identities.
First `up` creates it; later commands refuse a missing or mismatching marker. Never
adopt existing data. Each stack uses Compose project `ai-platform-poc-<stack>` and
`docker/poc.override.yml`. The override uses Compose `!reset` to clear fixed
container names and Postgres/Valkey host ports. Only API is published, on
`127.0.0.1:${POC_API_PORT}`. Up selects a free port and records it in the marker.
Project-named volumes are listed in the marker. Down removes only listed volumes
whose `com.docker.compose.project` label matches. Never touch the `ai-platform`
developer project or `ai-platform_pgdata`. This is the reviewed project deviation.

Capture order:
1. Acquire one platform-wide Postgres advisory lock in a dedicated live connection.
   Purge takes the same lock around plan/sign/delete; backup waits for in-flight
   purge. Ordinary writes and decision-chain locks remain independent. Any future
   object deletion must take this lock. Release on success, failure and cancellation.
2. Run `pg_dump -Fc` inside the postgres container. Write the dump to private
   `.poc/<stack>/staging/`, check its exit code and hash the file.
3. Restore the dump to an owned scratch database and derive schema head, row counts,
   object references and per-tenant chain heads there, never from later live reads.
   Count every application table (including tenants, principals, api_keys, policies,
   knowledge_bases, documents, jobs, outbox, processed_events, gateway_decisions,
   chain_heads and chain_checkpoints). Include zero-row tables and pending work.
4. Copy referenced content-addressed files after the dump. Rehash each file, reject
   missing/corrupt content and unsafe paths; concurrent new unreferenced files need
   not be included. Manifest v1 binds the dump SHA-256, each object key and hash,
   schema head, table counts, tenant chain positions/hashes/checkpoints, key id and
   public key, release-manifest SHA-256, stack identity, timestamp and today's
   tenant cost counters read via `valkey-cli GET`.
5. Write `manifest.json`, hash it and release the lock. Run one tagged `restic
   backup` of the staging folder. Bind the snapshot tag to the manifest hash.
   Repository is `.poc/<stack>/backups`, with a mounted 0600 password file.
   Publish latest only after validation. Any nonzero exit prevents publication.

Use restic 0.19.1 built from verified source in `docker/restic` under profile `backup`;
resolve the exact patch/index at implementation, with no placeholder accepted.
Backup storage is local; restic supports local and S3 directly, so no rclone.
`POC_RECOVERY_REF` is the snapshot ID, not a secret or an age override.
Before destruction, `down` stops API and worker. Its preflight order is marker →
ref equals latest completed backup → live row counts and tenant chain heads equal
the manifest → age at most `POC_BACKUP_MAX_AGE_SECONDS` → `restic check --read-data`
and scratch restore with all manifest checks. The age defaults to 86400 seconds
and can be overridden with a positive value. On mismatch, refuse with "data written
after backup; run poc backup". Any refusal restarts the services.
Bind proof to exact snapshot and manifest digests; serialize lifecycle mutations
and recheck ownership before deletion. Only then remove marker-owned runtime data
and compute. Preserve key, password, marker and backup repository for the next `up`.
`up` after teardown restores into fresh owned storage with API/worker stopped.
Verify all bindings, public key compatibility and chain continuity before starting
writers or reporting healthy; reject schema/release mismatch, never auto-upgrade
an incompatible restore. Compare counts/heads before health traffic adds decisions.
Failed restore stays unhealthy and preserves recovery material.

Valkey is excluded from the data snapshot. On a same-UTC-day restore, reapply each
manifest cost counter with `INCRBY` before API health; on a later day use new daily
counters. Rate-limit windows and cache entries are lost and listed in the restore
report. Report other lost Valkey state, including sessions, token counters, breaker
state and leases; sessions require sign-in again.
Jobs, run state, outbox and dedupe state come from Postgres, including expired-lease
reclaim. Rebuild caches lazily. The same-day restored cost counter preserves spending authority at the captured value.
Test and report any work not backed by Postgres as lost; do not invent a Valkey queue.

## WP4 — M0 drill and product docs
M0: complete journey. `scripts/showcase/m0.sh <stack>` delegates to Python; replace
its missing-drill SKIP with required `scripts/verify/poc-drill.sh <stack>`. Start with
`poc up`, use public fixture/persona setup, deny one alias, prove zero inference and
save receipt/public keys. Restore baseline before backup. Run backup, checked down,
up; use public `poc status --json` manifest verification for count/head comparisons.
Reverify saved receipts offline using trusted saved public keys, then one new
governed deny, decision and signature. No paid model is needed. Keep Modules-off
coverage and fail the entry point if any required step fails. Direct SQL belongs
only in the general backup product implementation and test fixtures. Required
stdout markers: `PASS backup`, `PASS checked down`, `PASS restored counts and heads`,
`PASS saved receipts offline`, `PASS new governed call`, `PASS restore drill`.
Print count/head comparison results without row contents or secrets.

No new HTTP route/action/event is planned. Any missing general seam is product
work with tests, not a showcase bypass. Schema changes, if needed, use the next free
forward migration with RLS/GRANT tests. Update operations, deployment, configuration,
architecture and generated references when implementation changes them, plus MAP,
CHANGELOG and the report. Infrastructure adds no console page.
