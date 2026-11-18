# Sprint 015: Threat model

Assets: tenant data, durable work, decision chains, saved receipts, private signing
key, restic password, release identity and unrelated laptop volumes.
Boundaries: operator → local subprocesses; host secret files → containers;
Postgres snapshot → object copy → restic repository; recovery → running services.

| Threat | STRIDE | Control | Exact test from test-spec.md |
|---|---|---|---|
| Inference escapes governance | Elevation | Required caller/context; explicit alias deny | `tests/unit/test_llm.py::test_missing_governed_caller_fails_closed`; `tests/unit/test_llm.py::test_missing_governance_context_fails_closed`; `tests/integration/test_llm_governance.py::test_citation_generation_records_every_attempt` |
| Mutable or platform-specific pin | Tampering | Validate index metadata and artifact bindings | `tests/unit/test_release_manifest.py::test_rejects_unpinned_and_platform_images`; `tests/unit/test_release_manifest.py::test_manifest_binds_local_build_and_indexes` |
| Secret theft or substituted file | Disclosure / Spoofing | Private no-follow files, secret mounts, exclusions | `tests/unit/test_poc_keys.py::test_refuses_unsafe_secret_files`; `tests/unit/test_poc_keys.py::test_secrets_never_leave_files` |
| Rotation breaks or forges old identity | Repudiation | Exact trusted prior public key; worker shares key | `tests/integration/poc/test_restore.py::test_wrong_key_id_requires_previous_public_key`; `tests/integration/poc/test_keys.py::test_api_worker_share_key_across_restart` |
| Purge races capture | Tampering / Repudiation | Shared advisory lock | `tests/integration/poc/test_backup.py::test_purge_waits_during_backup` |
| Online capture omits data | Tampering | Dump-derived manifest, immutable objects, hash every reference | `tests/integration/poc/test_backup.py::test_online_manifest_matches_dump_snapshot`; `tests/integration/poc/test_backup.py::test_missing_or_corrupt_object_refuses_backup` |
| Failed command produces plausible backup | DoS / Tampering | Propagate all exits, publish latest last | `tests/unit/test_poc_backup.py::test_failed_dump_command_never_publishes_backup` |
| Tampered recovery starts writers | Tampering | Verify every manifest binding before healthy | `tests/integration/poc/test_restore.py::test_manifest_tampering_blocks_health` |
| Wrong or stale recovery permits deletion | DoS | Ordered marker/ref/live-state/age/drill gates | `tests/unit/test_poc.py::test_down_checks_in_order`; `tests/unit/test_poc.py::test_down_refuses_writes_after_backup`; `tests/unit/test_poc.py::test_stale_backup_refuses_down`; `tests/unit/test_poc.py::test_recovery_ref_must_be_latest`; `tests/integration/poc/test_restore.py::test_restic_check_and_scratch_restore_gate_down` |
| Path/ownership/race deletes unrelated state | DoS / Elevation | Isolated project, override, labelled volumes, marker and lifecycle lock | `tests/unit/test_poc.py::test_stack_name_marker_and_local_runner`; `tests/unit/test_poc_compose.py::test_poc_override_resets_names_and_ports`; `tests/integration/poc/test_down.py::test_down_never_touches_dev_project_volumes`; `tests/integration/poc/test_down.py::test_ownership_and_lifecycle_races_refuse` |
| Empty Valkey loses work or widens budget | DoS / Elevation | Durable jobs/outbox, explicit losses, same-day cost counter restore | `tests/integration/poc/test_restore.py::test_valkey_loss_and_postgres_work_recovery`; `tests/integration/poc/test_restore.py::test_valkey_loss_does_not_reset_spending_authority` |
| Showcase bypass or false success | Elevation / Repudiation | Public seams, fatal drill failure, independent evidence | `tests/unit/refco/test_public_seams.py::test_lifecycle_uses_public_seams`; `tests/unit/refco/test_m0_lifecycle.py::test_required_drill_failure_is_fatal` |

Abuse cases include malformed stack paths, swapped key files, an older recovery
reference, killed dump process and teardown during backup. The named negative tests
must fail safely without deleting data or exposing secrets.
OWASP scope: authorization, secret management and integrity controls; agent/model
bypass coverage addresses ASI02 and LLM06. No new prompt or autonomous tool surface.
Residual risks: laptop loss also loses local backups unless the operator copies
them separately; private key recovery is the operator's job. Teardown refuses when live counts or chain heads differ from the snapshot. The
age limit also bounds backup age. Other uncounted changes remain a residual risk. Manifest
hashes plus restic authentication detect corruption, not a malicious operator with
the repository password. No maintenance mode or unrecorded-call exception exists.
