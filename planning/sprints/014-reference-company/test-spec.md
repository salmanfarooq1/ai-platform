# Sprint 014: Test specification

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Builders write each test with this name and expected result. They may add tests, but never change, skip or loosen a listed test. Tiers: **U** unit, **I** integration, **P** Playwright, **L** live local script run by the Architect.

## WP1: Personas
Journey step: Personas exist with their own keys.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 1.1 | `tests/integration/refco/test_personas.py::test_creates_six_personas` | I | In a fixture-owned test tenant, setup creates six principals and each key has the scopes in its persona file. | A1 |
| 1.2 | `tests/integration/refco/test_personas.py::test_rerun_reuses_and_never_regenerates` | I | Rerun creates no new principal or key. A revoked key causes exactly one replacement; `--replace <persona>` can force rotation. | A1, T2 |
| 1.3 | `tests/integration/refco/test_personas.py::test_keys_never_printed` | I | With sentinel capture of stdout and stderr, no full key appears. | A2, T1 |
| 1.4 | `tests/unit/refco/test_personas_files.py::test_keys_file_rules` | U | Refuse a symlinked key file and simulated foreign ownership; write mode 0600 in a mode 0700 directory by atomic rename. | A2, T3 |
| 1.5 | `tests/unit/refco/test_personas_files.py::test_ignored_everywhere` | U | `git check-ignore` and `.dockerignore` exclude `.showcase/`; no file under `planning/**/evidence/` contains a platform key (key-prefix pattern). The only exemptions are the two exact hand-built strings that `tests/e2e/test_tenancy.py` and `tests/unit/test_identity_key_listing.py` print (`gap_abcd1234_` + 43 `a`, `gap_abcdefgh_` + 43 `x`); they were never issued and appear in past evidence (Architect 2026-11-16: keep evidence as recorded). There is no `.evidenceignore` (Architect 2026-11-16: nothing reads it). | A2, T1 |
| 1.7 | `test_manifest_tenant_cannot_be_changed`, `test_tenant_must_match_fixture_credential`, `test_foreign_saved_key_is_never_revoked` | I | Foreign state or fixture credentials refuse writes; rotation never revokes another tenant's key. | A1, T2 |
| 1.8 | `tests/unit/refco/test_personas_files.py::test_state_dir_must_be_protected` | U | `--state-dir` is accepted only as the repo's `.showcase/` or an absolute path outside the worktree; a path inside the worktree elsewhere, or with an `evidence` path part, is refused before any write. | A2, T3 |
| 1.10 | `tests/integration/refco/test_personas.py::test_keys_never_printed_on_failure` | I | With a failure injected mid-run, the sentinel key is absent from stdout, stderr and logs; assertion messages never include the captured text. | A2, T1 |
| 1.6 | `tests/unit/refco/test_personas_files.py::test_only_existing_scopes` | U | Every persona scope is currently implemented. | A1 |

## WP2: M0 showcase
Journey step: The M0 script runs every M0 step and prints each result.

| ID | Test | Tier | Given / when / then | Proves |
|---|---|---|---|---|
| 2.1 | `tests/integration/refco/test_m0_restore.py::test_concurrent_change_is_not_overwritten` | I | Another writer advances the policy head after the journey sets it; restore leaves that head unchanged and prints a warning. | A3, T4 |
| 2.2 | `tests/integration/refco/test_m0_restore.py::test_restore_is_a_new_version` | I | The baseline is active at a version newer than the journey's version; no version was deleted. | A3 |
| 2.3 | `tests/integration/refco/test_m0.py::test_denied_search_makes_no_model_request` | I | A chat admission deny produces no chat or embedding request, and the recording Ollama request count is unchanged. | A3, T5 |
| 2.4 | `ui/e2e/showcase-m0.spec.ts` › `m0 journey` | P | Its own project, seed and server select the denied `model.invoke` decision explicitly (not the request link, which opens the first decision) and verify its receipt names `model_not_allowed`, and Platform > Modules shows agents off. | A4 |
| 2.5 | live `scripts/showcase/m0.sh` | L | Against the local stack, every M0 step prints a result; the denied search leaves the Ollama request count unchanged. | A3 |
| 2.6 | `tests/integration/refco/test_m0.py::test_ollama_reachable_only_through_recorder` | I | The M0 server's environment and catalog point every Ollama setting (catalog endpoint, `OLLAMA_API_BASE`, `OLLAMA_HOST`, `OLLAMA_URL`, SDK default `api_base`) at the recorder; a second recorder at the direct/default address receives zero requests during the journey. | A3, T5 |
| 2.7 | `tests/integration/refco/test_m0_restore.py::test_signal_restores_policy` | I | SIGTERM and SIGINT to the M0 runner after the deny version is set end with the baseline restored as a new version (row 2.1 lock rules still hold). | A3, T4 |


Review regressions: `test_identity_key_listing.py` verifies fresh app-role key listing under RLS and
same-principal foreign-key preservation with saved state, lost state and a lost manifest.
`test_public_seams.py` recursively guards showcase Python sources against database imports,
SQL literals and database method calls, with seeded negatives and private-import checks.
`test_policy_cas.py::test_two_concurrent_policy_writers` observes B's backend waiting on
`pg_stat_activity.wait_event_type = 'Lock'` before releasing A, with a failing timeout.
`test_review_regressions.py` covers lock polling/timeout and PATH/override/missing shell runners.
Catalog construction for recorder tests lives only in `test_m0.py`.
