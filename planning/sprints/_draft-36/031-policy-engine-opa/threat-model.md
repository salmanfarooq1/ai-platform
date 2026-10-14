# Sprint 031: Threat model
## Assets
- The policy bundle and its signing key.
- Tenant policy documents and persona policies.
- Stored policy inputs: hashes and structured facts only.
- The integrity of every allow and deny.

## Trust boundaries crossed
- Gateway to the OPA sidecar over the compose network.
- Bundle build (CI or operator) to the OPA runtime.
- Stored inputs and bundles to the offline replay tool.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | OPA is down or slow and the gateway allows by default | Elevation of privilege | Any error or timeout is `policy_unavailable`, a deny | `test_opa_down_denies` |
| T2 | A changed bundle is loaded into OPA | Tampering | A signed bundle with `--verification-key`, and a revision check against the expected hash at startup | `test_unsigned_bundle_refused`, `test_bundle_revision_mismatch_refuses_start` |
| T3 | Someone pushes a policy through OPA's REST API | Tampering | `--authorization=basic` with a system policy that refuses writes. Port bound to `127.0.0.1`. | `test_opa_write_api_refused` (verify script) |
| T4 | The two engines drift, so the default and OPA disagree | Tampering | One decision table run on both engines in CI | `test_decision_table_python`, `test_decision_table_opa` |
| T5 | Policy inputs store tool arguments or prompt text | Information disclosure | `PolicyInput` holds hashes and a validity flag only. A test scans the stored documents. | `test_policy_input_has_no_text` |
| T6 | A decision cannot be explained later | Repudiation | Bundle hash and input hash in the chained record. Stored input and bundle allow offline replay. | `test_offline_replay_matches` |
| T7 | "Approval required" is treated as allow before 034 | Elevation of privilege | It maps to `allowed=False` | `test_approval_required_is_deny` |
| T8 | OPA decision logs leak inputs | Information disclosure | Decision logs off. The console logger is not configured. | compose config test `test_opa_decision_logs_off` |

## Abuse cases
- An operator edits a Rego file on the host and restarts OPA. The revision no longer matches the signed hash, so the gateway refuses to start with OPA.
- A tenant admin crafts a policy whose purpose list widens a grant. The purpose check compares with the grant's purpose, not with the policy, and the table holds this case.

## OWASP items in scope
- ASI03 (Identity and privilege abuse): T1, T4 and T7.
- ASI04 (Agentic supply chain): the policy bundle as a supply-chain artifact (T2).
- LLM items: none. No model input or output changes here.

## Residual risks
- The bundle signing key in local mode is a file on the same host. Key separation comes in 040.
- Inputs recorded before this sprint have no stored input document, so they cannot be replayed.
