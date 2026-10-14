# Sprint 012: Threat model
## Assets
- The decision chain and receipts (integrity of history).
- Routes of each module, and the rule that every call goes through `enforce()`.

## Trust boundaries crossed
- Caller to a route of a disabled module.
- Gateway to evidence core through the `DecisionSink` port.
- Old (version 1) to new (version 2) records in one chain.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A disabled module leaves a route, a job handler or the MCP mount open. | Elevation of privilege | The registry mounts a deny handler for every path prefix of a disabled module, and the worker skips its job kinds. A test lists every app route and maps it to a module. | `test_module_disabled.py::test_every_route_of_a_disabled_module_is_denied`; `::test_worker_does_not_claim_disabled_job_kinds`. |
| T2 | Chain verification breaks for old records after the change. | Repudiation | Version 1 hashing is unchanged; version is a column, defaulted to 1. | `test_record_v2.py::test_v1_rows_verify_unchanged`; `test_migration_record_v2.py`. |
| T3 | Extension values change on a JSONB round-trip, so a stored record no longer matches its hash. | Tampering | Registered keys, JSON Schema per key, no floats, size limit. | `test_record_v2.py::test_float_extension_refused`; `::test_extension_order_does_not_change_hash`. |
| T4 | Moving the record code loses the fail-closed path. | Elevation of privilege | `enforce()` treats any sink error on an allow as a deny. | `test_decision_sink_contract.py::test_failure_raises`; `test_gateway_enforce.py` fail-closed cases. |
| T5 | A module imports another module's internals, so switching one off breaks or bypasses the other. | Tampering | import-linter contracts in CI. | `test_import_contracts.py`. |
| T6 | A disabled-module request leaves no trace. | Repudiation | The deny is recorded with `module_disabled`. | `test_module_disabled.py::test_deny_is_recorded`. |

| T7 | The single-tenant shape is read as "no isolation needed", and a later change weakens RLS or tenant checks. | Information disclosure | The shape changes only tenant creation and the UI. RLS and `tenant_connection` stay in both shapes. | `test_deploy_shape.py::test_rls_present_in_both_shapes`; the existing RLS suite runs under both shapes. |

## Abuse cases
- A client calls `/v1/sandbox/runs/...` or `/v1/mcp/sse` on a Gateway edition. It gets 404 `module_disabled` and a deny row.
- A future sprint adds an extension key with a float score. The registry refuses it at write time, so it never reaches the chain.

## OWASP items in scope
- ASI03 (identity and privilege abuse): a disabled module grants nothing.
- ASI10 (rogue agents): agent routes and job kinds are really off when the agents module is off.
- LLM: none. No model behaviour changes.

## Residual risks
- import-linter sees static imports only. The existing AST lint still catches `importlib` calls for SDKs, not for modules.
- Nav hiding is cosmetic. The route deny is the control.
