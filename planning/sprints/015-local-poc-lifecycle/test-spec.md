# Sprint 015: Test specification

Write these tests and capture their failing results before implementation. Add
coverage freely; never skip, xfail or weaken assertions. U = unit, I = real local
Postgres/Valkey with fake models, P = Playwright, L = real lifecycle entry point.
All paths below are exact node IDs. Parameterized cases are mandatory.

## WP0 — M0 explicit deny before inference (A0)
| Test | Tier | Assertion |
|---|---|---|
| `tests/integration/refco/test_m0.py::test_reference_company_seed_allows_models` | I | Reference-company server starts with `allowed_models: "*"`; seed creates no deny version. |
| `tests/integration/refco/test_m0.py::test_journey_denies_only_selected_alias` | I | Publish through `publish_journey_policy`; selected alias denies, another baseline-allowed alias stays allowed, all other policy fields stay equal; inference count stays zero for deny. |
| `tests/integration/refco/test_m0_restore.py::test_explicit_deny_restores_on_failure` | I | Inject failure after explicit deny; baseline returns as a new version; a concurrent head is preserved and conflict reported. |
| `tests/unit/test_playwright_config.py::test_poetry_resolves_from_environment` | U | Evaluate both showcase server configurations using a PATH sentinel and a POETRY override (including a spaced path); both select that executable; missing executable fails clearly; no host path literal. |
| `tests/unit/test_llm.py::test_missing_governed_caller_fails_closed` | U | Omit caller or pass None to both generation functions: exception before any provider call, including with nonempty chunks. |
| `tests/unit/test_llm.py::test_missing_governance_context_fails_closed` | U | Omit context or pass None to both functions with a caller: fail before caller/provider work. |
| `tests/integration/test_llm_governance.py::test_citation_generation_records_every_attempt` | I | Allowed generation records governed attempts and retains citation/usage semantics; policy deny and decision-write failure cause zero provider calls; retry attempts each require governance. |
| `ui/e2e/showcase-m0.spec.ts` › `m0 journey` | P | Assert baseline allowed, explicitly publish alias deny using the same operator helper as M0, ask and inspect the denied model decision/verified receipt and Agents off; finally restore baseline and verify a new version, even on failure. |

Existing citation, prompt, cost, truncation and retry tests remain. Route them
through a real governed caller with fake ports. The old 35-second retry expectation
belongs to the removed fallback; replace it explicitly with ModelCaller's bounded
retry contract, retaining attempt-count and error-propagation assertions. Document
that expectation correction, never silently remove the regression.

## WP1 — M0 one-command up (A1, A-mem)
| Test | Tier | Assertion |
|---|---|---|
| `tests/unit/test_poc_compose.py::test_default_services_and_hardening` | U | Default set is exactly postgres/valkey/api/worker; API/worker share artifact, read-only root, ALL capabilities dropped, no-new-privileges, writable mounts limited and healthchecks present; API binds loopback. |
| `tests/unit/test_release_manifest.py::test_rejects_unpinned_and_platform_images` | U | Mutate each Compose profile and Dockerfile base to floating tag, placeholder, malformed digest and real child-manifest metadata; each refuses before launch. |
| `tests/unit/test_release_manifest.py::test_manifest_binds_local_build_and_indexes` | U | Manifest records verified external indexes, selected platforms, pinned build inputs, Compose hash and honest local app output ID; stale/tampered manifest, changed image or unavailable index proof refuses up. |
| `tests/integration/poc/test_up.py::test_fresh_up_initializes_default_stack` | I | One real `poc up` initializes owned empty state, migrates, starts four healthy services as app role; ambient optional profiles stay off; repeat up is idempotent. |
| `tests/integration/poc/test_up.py::test_hardened_services_are_healthy` | I | API serves health and worker runs a durable job with read-only roots; inspect actual security settings and capture `docker stats --no-stream` for both and the on-demand restic service. |

| `tests/unit/test_poc_compose.py::test_poc_override_resets_names_and_ports` | U | Override clears fixed container names and Postgres/Valkey host ports with `!reset`; only API binds loopback on the selected port. |

## WP2 — M0 stable receipt identity (A2)
| Test | Tier | Assertion |
|---|---|---|
| `tests/unit/test_poc_keys.py::test_key_created_once_and_survives_down` | U | Atomic exclusive generation yields 0600 key in 0700 directory; repeated up and successful down preserve bytes; restoring with no key refuses generation. |
| `tests/unit/test_poc_keys.py::test_refuses_unsafe_secret_files` | U | Symlinked parent/file, foreign owner, permissive modes and malformed key refuse; key/password excluded by git and Docker ignores. |
| `tests/unit/test_settings.py::test_receipt_signing_key_file` | U | Settings load valid file; missing/unreadable/malformed file or inline-plus-file conflict fails without revealing contents; existing inline and previous-public-key inputs still work. |
| `tests/unit/test_poc_keys.py::test_secrets_never_leave_files` | U | Sentinel key/password absent from argv, environment values, Compose render, logs, errors, evidence and backup payloads on success and failure; mounts expose only paths. |
| `tests/integration/poc/test_keys.py::test_api_worker_share_key_across_restart` | I | API receipt and worker purge checkpoint have the same public key id before/after restart; saved receipts verify offline using saved trusted public keys. |
| `tests/integration/poc/test_restore.py::test_wrong_key_id_requires_previous_public_key` | I | Wrong active key refuses restore; exact old public bytes in previous keys permits it and old receipts verify; fabricated id, altered bytes or absent private key refuses; new receipt uses active key. |

## WP3 — M0 backup/down/up (A3, A4)
| Test | Tier | Assertion |
|---|---|---|
| `tests/unit/test_poc.py::test_stack_name_marker_and_local_runner` | U | Missing name, regex boundary failures, traversal, remote context and foreign/missing marker refuse before tool calls (first up may create marker); Runner uses argv, never shell interpolation. |
| `tests/unit/test_poc.py::test_down_checks_in_order` | U | Inject each failed gate; trace is marker → latest ref → live counts/heads → age → read-data check + scratch restore; writers stop first, services restart on refusal; no deletion on any failure; successful deletion touches only owned runtime volumes/containers, retaining secrets/backups/marker. |
| `tests/unit/test_poc.py::test_stale_backup_refuses_down` | U | Frozen clock tests default 86400 seconds, a positive override, invalid values, expired backup and future timestamp; invalid or stale cases refuse; exact boundary passes. |
| `tests/unit/test_poc.py::test_down_refuses_writes_after_backup` | U | Changed live row counts or tenant chain heads refuse with "data written after backup; run poc backup"; no deletion and services restart. |
| `tests/unit/test_poc.py::test_recovery_ref_must_be_latest` | U | Missing, older, incomplete, wrong-stack or changed latest ref refuses; successful proof binds the snapshot and manifest digests. |
| `tests/unit/test_poc_backup.py::test_restic_service_contract` | U | Official 0.19.x index-pinned restic is backup-profile only; local repo and password-file mounts; one tagged backup contains the staged dump, objects and manifest; no rclone or Docker socket. |
| `tests/unit/test_poc_backup.py::test_failed_dump_command_never_publishes_backup` | U | Partial dump then nonzero exit, restic failure or cancellation yields failure, releases locks, cleans private staging and never advances latest; original process exit status is checked. |
| `tests/integration/poc/test_backup.py::test_purge_waits_during_backup` | I | Two connections prove purge waits/skips before plan/sign/delete while capture owns lock; an in-flight purge delays capture; errors/cancellation release lock and purge resumes. |
| `tests/integration/poc/test_backup.py::test_online_manifest_matches_dump_snapshot` | I | Concurrent ordinary writes and governed calls continue and remain recorded; scratch dump supplies exact schema, all table counts, pending work, tenant heads/checkpoints and object set; manifest binds dump/public key/release; post-snapshot rows excluded. |
| `tests/integration/poc/test_backup.py::test_missing_or_corrupt_object_refuses_backup` | I | Dump references absent, wrong-hash or unsafe-path content: capture fails without publishing latest; concurrent new objects do not affect completeness. |
| `tests/integration/poc/test_restore.py::test_manifest_tampering_blocks_health` | I | Independently alter schema, dump bytes, object bytes, row count, tenant head/checkpoint, key metadata and release digest; verification fails before writers start/healthy; no existing target is overwritten. |
| `tests/integration/poc/test_restore.py::test_restic_check_and_scratch_restore_gate_down` | I | Real read-data check and real scratch restore pass intact set; damaged restic data or injected restore failure refuses down and leaves runtime data/secrets intact. |
| `tests/integration/poc/test_restore.py::test_restore_reproduces_manifest_before_writers` | I | Fresh owned restore matches all table counts, object hashes and chain heads/continuity; only then start API/worker; repeated up does not restore over current data. |
| `tests/integration/poc/test_restore.py::test_valkey_loss_and_postgres_work_recovery` | I | Restore with empty Valkey reports every lost class, invalidates old session, rebuilds cache/index; Postgres queued ingest/agent jobs, expired leases and outbox resume with dedupe. Any non-durable pending work is explicitly reported lost. |
| `tests/integration/poc/test_restore.py::test_valkey_loss_does_not_reset_spending_authority` | I | Capture each tenant cost counter with `valkey-cli GET`; same-day restore uses `INCRBY` before health, and a tenant at its cap remains denied. A later UTC day starts a new counter. |
| `tests/integration/poc/test_down.py::test_down_never_touches_dev_project_volumes` | I | Refuse a marker-listed volume labelled for `ai-platform`; preserve `ai-platform_pgdata` and all developer volumes. |
| `tests/integration/poc/test_down.py::test_ownership_and_lifecycle_races_refuse` | I | Symlink/foreign volume, protected old volume, active restore target, concurrent backup/down or changed proof cannot cause deletion; lifecycle lock serializes mutations and owner mismatch refuses. |

## WP4 — M0 full drill (A5)
| Test | Tier | Assertion |
|---|---|---|
| `tests/unit/refco/test_m0_lifecycle.py::test_required_drill_failure_is_fatal` | U | Fake Runner shows up → backup → checked down → restore up → compare → offline receipt verify → new governed call; missing drill, missing prerequisites or any failed step makes shell entry exit nonzero, never successful SKIP. |
| `tests/integration/refco/test_m0_lifecycle.py::test_saved_receipts_and_new_call_after_restore` | I | Real restored fixture compares snapshot counts/heads before new traffic; saved deny receipt verifies offline and a new deny adds a decision/signed receipt with zero inference. |
| `tests/unit/refco/test_public_seams.py::test_lifecycle_uses_public_seams` | U | Seed private imports, product SQL and global SDK overrides into journey/helper sources: guard rejects each; actual lifecycle uses API/CLI/public admin only. |
| `scripts/showcase/m0.sh <stack>` | L | Real default stack, actual restic/Postgres backup and checked destructive teardown on fixture-owned data, restore up, full fixture teardown, count/head comparison, offline saved receipts, new governed call and Modules off all PASS; required blueprint PASS markers and no SKIP. |

## Evidence and regression gate
`accept.sh` runs all listed pytest files via full unit/live tiers, explicitly runs
`tests/integration/poc` and the refco/citation live files, runs the named browser
project and the real shell entry. The combined unit/integration/e2e JUnit goes through the existing exact
skip allowlist; new lifecycle files and required journey steps allow zero skips.
Capture baseline counts with `accept.sh --baseline` before code; preserve baseline
logs and JUnit. Final acceptance reports test delta and both models' review verdicts.
Missing tools/services are failing prerequisites, never invented passing evidence.
