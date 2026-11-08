# Sprint 014: Threat model

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

| # | Threat | STRIDE | Control | Test |
|---|---|---|---|---|
| T1 | A persona key leaks to logs, terminal output, a browser trace or evidence. | Information disclosure | Keys stay in the private `.showcase/keys.env`; private setup state is excluded from build contexts and artifacts. | `test_personas.py::test_keys_never_printed`; sentinel scan |
| T2 | Setup creates another tenant or silently regenerates a revoked key. | Elevation of privilege | Use a verified fixture-owned tenant. Never create tenants. Stop on invalid credentials; replacement is explicit. | `test_personas.py::test_rerun_reuses_and_never_regenerates` |
| T3 | A symlink or foreign-owned path redirects the key file. | Tampering | Reject symlinks and foreign ownership; write atomically in a private directory. | `test_personas_files.py::test_keys_file_rules` |
| T4 | The showcase overwrites a policy changed by another writer. | Tampering | Restore only when the head remains the journey's own version; create a new version. | `test_m0_restore.py::test_concurrent_change_is_not_overwritten` |
| T5 | A denied model call still reaches inference. | Information disclosure | Sprint 013 admission denies before model I/O; compare Ollama request count around the denied search. | `test_m0.py::test_denied_search_makes_no_model_request`; live `m0.sh` |
