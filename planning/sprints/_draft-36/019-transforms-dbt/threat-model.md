# Sprint 019: Threat model

## Assets
- The worker process and its host (dbt runs Jinja and Python).
- Short-lived catalog and S3 credentials for one tenant.
- Tenant marts in DuckLake.
- The vendored package tree.

## Trust boundaries crossed
- Tenant-supplied template parameters become rendered SQL that dbt runs.
- The worker hands secrets to a dbt subprocess.
- dbt reads package code from disk.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A parameter injects Jinja or SQL (`{{ ... }}`, `'; DROP`) and runs code in the worker | Elevation of privilege | Identifier regex, typed scalars, refused characters, sandboxed Jinja with no globals | `test_transform_generate.py::test_injection_parameters_refused` |
| T2 | A user-written model, macro or Python model reaches dbt | Elevation of privilege | Only platform templates are rendered; the generator refuses any other file | `test_transform_generate.py::test_only_templates_rendered` |
| T3 | A malicious or changed package runs code | Tampering | `packages.lock` with tree hash, `local:` entries only, pre-check before dbt | `test_dbt_packages.py::test_unlisted_package_refused`, `test_hash_mismatch_refused` |
| T4 | `dbt deps` or an extension download reaches the network | Tampering | Offline deps; extensions preinstalled; network guard in tests | `test_dbt_packages.py::test_deps_offline` |
| T5 | Secrets end up in `profiles.yml`, logs or artifacts | Information disclosure | `env_var()` only; 0600 temp dir deleted in `finally`; scan for secret values | `test_dbt_secrets.py::test_no_secret_in_artifacts` |
| T6 | dbt attaches another tenant's catalog | Information disclosure | Profile built from the job's tenant only; credentials scoped to that tenant's catalog and prefix | `test_dbt_secrets.py::test_cross_tenant_attach_fails` |
| T7 | Two writers corrupt a mart or one aborts | Tampering | Advisory lock per target dataset in sorted order, retry on conflict | `test_dbt_writer_lock.py::test_concurrent_runs_serialised` |
| T8 | A runaway model holds the worker | Denial of service | `DBT_RUN_TIMEOUT_SECONDS`; DuckDB `memory_limit` and `threads` in the profile | `test_dbt_finance_marts.py::test_timeout_kills_run` |
| T9 | dbt telemetry sends data out | Information disclosure | Env allowlist with `DO_NOT_TRACK=1` and usage stats off | `test_dbt_secrets.py::test_subprocess_env_allowlist` |
| T10 | Stored lineage events leak SQL literals | Information disclosure | Literals stripped before insert, hashes only | `test_lineage_raw_events.py::test_no_literals_stored` |

## Abuse cases
- A producer sets a template parameter to `x }}{{ run_query('COPY ...') }}`. Refused with 422.
- Someone drops a new folder into `vendor/` without updating the lock. The run fails with `package_not_allowed`.

## OWASP items in scope
- ASI05 Unexpected Code Execution: T1, T2, T3. dbt is code execution; only platform code runs.
- ASI04 Agentic Supply Chain: T3, T4 (vendored, hashed packages).
- LLM Top 10: none. No model is called.

## Residual risks
- dbt and dbt-duckdb themselves are trusted code at the pinned versions.
- The subprocess shares the worker's kernel. A dbt sandbox is a later program step.
