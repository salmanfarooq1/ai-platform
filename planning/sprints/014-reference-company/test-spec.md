# Sprint 014: Test specification

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Builders write each test with this name and expected result. They may add tests, but never change, skip or loosen a listed test. Tiers: **U** unit, **I** integration, **P** Playwright, **L** live local script run by the Architect.

## WP1: Personas
Journey step: Personas exist with their own keys.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 1.1 | `tests/integration/refco/test_personas.py::test_creates_six_personas` | I | In a fixture-owned test tenant, setup creates six principals and each key has the scopes in its persona file. | A1 |
| 1.2 | `tests/integration/refco/test_personas.py::test_rerun_reuses_and_never_regenerates` | I | Rerun creates no new principal or key. A revoked key stops setup; `--replace <persona>` creates exactly one replacement key. | A1, T2 |
| 1.3 | `tests/integration/refco/test_personas.py::test_keys_never_printed` | I | With sentinel capture of stdout and stderr, no full key appears. | A2, T1 |
| 1.4 | `tests/unit/refco/test_personas_files.py::test_keys_file_rules` | U | Refuse a symlinked key file and simulated foreign ownership; write mode 0600 in a mode 0700 directory by atomic rename. | A2, T3 |
| 1.5 | `tests/unit/refco/test_personas_files.py::test_ignored_everywhere` | U | `.showcase/` is excluded from git, Docker/build contexts and evidence artifacts. | A2, T1 |
| 1.6 | `tests/unit/refco/test_personas_files.py::test_only_existing_scopes` | U | Every persona scope is currently implemented. | A1 |

## WP2: M0 showcase
Journey step: The M0 script runs every M0 step and prints each result.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 2.1 | `tests/integration/refco/test_m0_restore.py::test_concurrent_change_is_not_overwritten` | I | Another writer advances the policy head after the journey sets it; restore leaves that head unchanged and prints a warning. | A3, T4 |
| 2.2 | `tests/integration/refco/test_m0_restore.py::test_restore_is_a_new_version` | I | The baseline is active at a version newer than the journey's version; no version was deleted. | A3 |
| 2.3 | `tests/integration/refco/test_m0.py::test_denied_search_makes_no_model_request` | I | A chat admission deny produces no chat or embedding request, and the recording Ollama request count is unchanged. | A3, T5 |
| 2.4 | `ui/e2e/showcase-m0.spec.ts` › `m0 journey` | P | Its own project, seed and server show the model deny and receipt, and Platform > Modules shows agents off. | A4 |
| 2.5 | live `scripts/showcase/m0.sh` | L | Against the local stack, every M0 step prints a result; the denied search leaves the Ollama request count unchanged. | A3 |

