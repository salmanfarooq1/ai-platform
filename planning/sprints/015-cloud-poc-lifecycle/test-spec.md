# Sprint 015: Test specification

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Builders write the named tests with the specified results. They never skip, remove or loosen a test. Tiers: **U** unit, **I** integration, **D** local drill run by the Architect.

## WP1: Release manifest and wheelhouse
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 1.1 | `tests/unit/test_release_manifest.py::test_unresolved_placeholder_refuses` | U | A local bundle with an unresolved digest placeholder makes `poc up` stop before starting services. | A1, T2 |
| 1.2 | `tests/unit/test_release_manifest.py::test_digest_mismatch_refuses` | U | A manifest digest that differs from the inspected local image id is refused. | A1, T2 |
| 1.3 | `tests/unit/test_release_manifest.py::test_local_build_is_labelled` | U | A local image manifest has `source: local-build`. | A1 |
| 1.4 | `tests/unit/test_compose.py::test_app_image_installs_from_wheelhouse` | U | The app Dockerfile installs with `pip install --no-index --find-links`. | A2 |

## WP2: Maintenance and backup
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 2.1 | `tests/integration/test_maintenance.py::test_blocks_before_enforce` | I | During capture, non-health requests return 503 before `enforce()` and create no decision row. | A4, T3, T5 |
| 2.2 | `tests/integration/test_maintenance.py::test_admin_only_and_bounded` | I | A non-admin cannot change maintenance. An admin can turn it on and off, both changes are recorded, and the bounded setting ends maintenance. | A4 |
| 2.3 | `tests/integration/test_backup.py::test_manifest_binds_the_set` | I | The manifest lists schema head, database dumps, object hashes, key ids, row counts and chain heads; listed files exist in the backup. | A4 |
| 2.4 | `tests/integration/test_backup.py::test_failure_ends_maintenance` | I | An injected capture failure ends maintenance and marks the backup failed. | A4, T6 |
| 2.5 | `tests/integration/test_restore.py::test_restore_keeps_signing_key` | I | Restore into fresh state keeps the backup key id, verifies an old receipt and refuses a backup missing the key. | A5, T4 |

## WP3: Local POC commands
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 3.1 | `tests/unit/test_poc.py::test_commands_are_local_only` | U | `up`, `backup`, `down` and `status` use the local host; remote targets and SSH are rejected. | A3, T1 |
| 3.2 | `tests/unit/test_poc.py::test_no_shell_interpolation` | U | Subprocess calls use argument lists; no `shell=True` or `os.system` appears. | A3 |
| 3.3 | `tests/unit/test_poc.py::test_runner_wraps_local_tools` | U | The Runner invokes `docker compose`, `restic` and `rclone` with the local backup folder. | A3 |
| 3.4 | `tests/unit/test_poc.py::test_stack_name_and_marker` | U | A missing or invalid stack name, or a marker that does not match, refuses every command before any Runner call. | A3 |
| 3.5 | `tests/unit/test_poc.py::test_down_checks_in_order` | U | `down` refuses when the marker, the recovery reference, the backup age or the test restore fails, checked in that order; on success it removes only what the marker names. | A3 |
| 3.6 | `tests/unit/test_poc.py::test_secrets_never_in_args_or_logs` | U | The sentinel restic password never appears in Runner arguments, logs or evidence; secret files are created 0600. | A3 |

## WP4: Restore drill
Journey step: `poc up`, `poc backup`, `poc down`, `poc up` restores the stack with its signing key.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 4.1 | `scripts/verify/poc-drill.sh` | D | Architect runs the local up, backup, down, up drill; row counts, chain heads, old receipt and signing-key id match. Captured output is saved as `evidence/drill.txt`. | A5 |

