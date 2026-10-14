# Sprint 046: Threat model
## Assets
- Persona API keys and session state created by the scripts.
- The reader's trust in public page claims.
- The developer's machine running the scripts.

## Trust boundaries crossed
- Scripts to the local API and to Docker.
- Fresh clone to image registries and the model registry (first pull).
- Public pages to visitors.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Persona keys printed to the terminal or committed | Information disclosure | Keys written once to git-ignored `.showcase/` with mode `0600`; scripts print key prefixes only | `test_showcase_state_is_gitignored`, `test_showcase_scripts_do_not_echo_keys` |
| T2 | A script deletes the developer's real volumes | Tampering | Compose project `showcase`; teardown only with `-p showcase`; shellcheck plus a grep test for `down -v` without `-p showcase` | `test_showcase_teardown_scoped` |
| T3 | A public page claims a feature that is not built | Repudiation | `copy-check` maps each claim to a may-claim item with a named test | `npm run copy-check` |
| T4 | Synthetic data looks like real people or brands | Information disclosure | Reference company deny-list scan from Sprint 015 runs on the walkthrough output | `test_reference_data_deny_list` |
| T5 | A fresh clone pulls a changed image or model | Tampering (supply chain) | Digests from compose and `models.lock`; the models check runs in `all.sh` | `test_all_sh_runs_models_lock_check` |
| T6 | A journey passes by skipping a step | Repudiation | Each script exits non-zero on the first failed step; the spec asserts the step count | `test_showcase_scripts_fail_fast` |

## Abuse cases
- A visitor copies a landing page claim into a sales deck. The claim links to a built, tested item only.
- A developer runs `all.sh` on a laptop with other projects. Only the `showcase` project is started and stopped.

## OWASP items in scope
- The MB and MC journeys exercise ASI01 (goal hijack through the poisoned PDF), ASI02, ASI03, ASI06, ASI07 and ASI09 tests from earlier sprints. No new control here.
- LLM09 Misinformation: public copy limited to built and tested claims.

## Residual risks
- Heavy journeys (`mc1.sh` with identity and policy, `mc2.sh` with guard) may not fit a CI runner and run nightly only.
- A local-model run on CPU is slow and can time out; the fake model run is the gate.
