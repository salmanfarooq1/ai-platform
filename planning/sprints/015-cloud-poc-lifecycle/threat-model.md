# Sprint 015: Threat model

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

| # | Threat | STRIDE | Control | Test |
|---|---|---|---|---|
| T1 | `poc` targets a remote or unintended host. | Tampering / DoS | Commands target the local host only through the local `Runner`. No SSH or cloud target is accepted. | `test_poc.py::test_local_target_only` |
| T2 | An unresolved or changed image is used. | Tampering | The manifest pins image digests; unresolved placeholders and mismatches stop `up`. | `test_release_manifest.py` |
| T3 | Backup data is inconsistent because writes continue. | Tampering / Repudiation | Maintenance blocks requests before `enforce()`; workers and relays pause during capture. | `test_maintenance.py` |
| T4 | The signing key changes during restore and old receipts fail. | Repudiation | Restore uses the key in the backup and refuses if it is missing. | `test_restore.py::test_restore_keeps_signing_key` |
| T5 | Maintenance denials are mistaken for recorded gateway decisions. | Repudiation | Accepted exception: non-health requests receive 503 before `enforce()` and create no decision row during capture. Maintenance changes are recorded decisions. | `test_maintenance.py::test_capture_denial_has_no_decision` |
| T6 | A failed capture leaves maintenance enabled. | DoS | Every capture failure ends maintenance and marks the backup failed. | `test_backup.py::test_failure_ends_maintenance` |
