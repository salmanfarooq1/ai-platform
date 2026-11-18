# Sprint 015: Pre-start review

The Architect reviews the pack before any builder starts. It checks the pack against the milestone goal, the real code and the web facts.

- **Review 1** (2026-11-17, Opus): the old cloud pack. It found 3 owner decisions; all were approved, and Sol rewrote the pack.
- **Review 2** (2026-11-17 02:50, Opus): Sol's rewrite. It found the items below. All are Architect-resolved, so none needs the owner.

## Goal check
M0 closes when a laptop can do: `poc up` → a call is denied with a signed receipt → `poc backup` → `poc down` → `poc up` → the same data comes back, and old receipts still verify offline.
- Every WP moves one step of that journey. Nothing in the pack is cloud work.
- The pack serves the goal.

## Web facts checked (Haiku agent, sourced)
- pg_dump is consistent while writes continue, and it does not block them. Its client version must be ≥ the server's, so we run it inside the server container.
- restic 0.19.1 is the latest release (2026-07-05). The upstream image was originally selected; WP4 fix round 5 replaces it with the source build in `docker/restic` to address fixed vulnerabilities.
- restic writes natively to a local folder and to S3. No rclone is needed.
- Keeping the private key out of the data backup is standard practice.
- Excluding the cache is normal when Postgres is the source of truth.

## Findings and resolutions

### R1. Capture is overbuilt
**What Sol wrote.** A stdin-reader snapshot of the dump plus a second, linked snapshot.
- That means two snapshots that must reference each other.
- That is more failure modes, and harder restores.

**Resolution.** One staging folder, and one snapshot.
1. Take the advisory lock.
2. Run `pg_dump -Fc` inside the postgres container. Write it to `.poc/<stack>/staging/`, check the exit code and hash the file.
3. Restore the dump into a scratch database. Derive the row counts and chain heads from that scratch database, not from live tables, so the counts match the dump exactly.
4. Copy the referenced objects into staging, then hash-check every one.
5. Write `manifest.json` (v1).
6. Release the lock.
7. Run one `restic backup` of the staging folder. The snapshot gets a tag, and the manifest records its hash.

Any non-zero exit means no snapshot is published, and `latest` is never moved.

### R2. The `down` check should prove "nothing changed since the backup"
**Why.** Age alone lets a backup taken 5 minutes ago miss 5 minutes of writes. The real danger is data written after the backup.

**Resolution.** Before any destructive step, `down`:
1. stops the api and worker, so no new writes arrive;
2. reads the live row counts and per-tenant chain heads;
3. requires them to equal the manifest.

On any mismatch it refuses with "data written after backup; run poc backup".

**Check order.**
1. stack marker
2. `POC_RECOVERY_REF` is the latest backup
3. live state equals the manifest
4. age ≤ `POC_BACKUP_MAX_AGE_SECONDS`
5. `restic check --read-data` plus a scratch restore have passed

The age limit defaults to 86400 (24h) and can be overridden. That closes **S015-backup-age**: no required variable, and a safe default.

A refusal starts the services again.

### R3. The stack's identity
**Problem.** The default services set fixed `container_name` values: `postgres`, `worker` and others. The corpus scripts use `docker exec postgres`. A second stack on the same laptop would therefore collide.

**Resolution.** This closes **S015-ownership**.
- **Project and override.** `poc` runs every stack as compose project `ai-platform-poc-<stack>`, with the override file `docker/poc.override.yml`. The override:
  - uses Compose `!reset` to clear `container_name` and the host port bindings of postgres and valkey;
  - publishes only the api, on `127.0.0.1:${POC_API_PORT}`.
- **Port.** The stack marker records `POC_API_PORT`. `poc up` picks a free port and stores it.
- **Volumes.** They are named by the project and listed in the marker. `down` removes only the volumes listed in the marker, and only when the label `com.docker.compose.project` matches.
- **The developer stack is never touched.** That is project `ai-platform`, with `ai-platform_pgdata`. A test asserts that `poc down` refuses any volume of project `ai-platform`.

**Deviation, flagged to the owner.** This adds per-stack compose projects beside the one `ai-platform` dev project.

**Why it is right.** A client's POC must be isolated, disposable and safe to tear down. Sharing the dev project's volumes would put the owner's data one bug away from deletion. A second client would need this too (rule 10).

### R4. Valkey loss and spending authority (narrowed)
**What the code does.**
- The daily cost cap lives only in Valkey, under the key `cost:<tenant>:<UTC day>` (`gateway/limits.py`).
- `usage_log` has no tenant column, so Postgres cannot rebuild the counter.

**What the old requirement asked for.** "Reconcile from Postgres or deny". That needs new product schema, which is overbuilt for M0.

**Resolution.**
- **Backup.** The manifest records today's cost counters for each tenant. They are read with `valkey-cli` inside the valkey container, through `GET`.
- **Restore.** If the restore runs on the same UTC day, it re-applies each counter with `INCRBY`, before the api reports healthy. On a later day, the counter is new anyway.
- **What is still lost.** Rate-limit windows (they last seconds) and cache entries. The restore report lists both.
- **Test.** `test_valkey_loss_does_not_reset_spending_authority` keeps its name. Its new assertion: after a same-day restore, a tenant at its cap is still denied.

### R5. Smaller fixes
- **builder-brief.** "Every launch needs owner approval" conflicts with CLAUDE.md rule 4, one go-ahead per sprint. The owner approved 015 on 2026-11-17, and the Architect launches.
- **The model routing stands.** Terra builds WP0, WP1 and WP4, and Sol reviews them. Sol builds WP2 and WP3, and Terra reviews them.
- **accept.sh.** `required_drill` must not need `POC_BACKUP_MAX_AGE_SECONDS`, because R2 gives it a default. It defaults `POC_STACK` to `m0drill`. The drill stack is fixture-owned and fully torn down at the end.
- **test-spec.** Remove the linked-snapshot tests. Add these:
  - `tests/unit/test_poc.py::test_down_refuses_writes_after_backup`
  - `tests/integration/poc/test_down.py::test_down_never_touches_dev_project_volumes`
  - `tests/unit/test_poc_compose.py::test_poc_override_resets_names_and_ports`
- **threat-model.** Keep its test names in step with test-spec.
- **acceptance.** A3 now names the live-state check.
- **QUESTIONS.** S015-backup-age and S015-ownership are moved to resolved, with the reasons above.

## Second look after the edits
To do before launch: re-read the edited blueprint, test-spec, threat-model and accept.sh, and confirm R1–R5 landed. The result is recorded below.

Second look: R1–R5 are reflected in the blueprint, test specification, threat model
and acceptance script. The threat-model nodes are a subset of the test-spec nodes.
`bash -n accept.sh` passes. Implementation and live checks remain before acceptance.
