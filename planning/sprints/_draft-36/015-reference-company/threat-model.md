# Sprint 015: Threat model
## Assets
- Persona API keys (the operator key holds `admin`).
- The generated data, which looks like PII and salaries.

## Trust boundaries crossed
- Showcase scripts to the API with persona keys.
- The host to the `refco-source` database.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | Fixture data matches a real person, company or email address. | Information disclosure | Syllable names, reserved email domains, fictional phone range, `TEST-` ids, deny list. | `test_refco_deny_list.py`. |
| T2 | Persona keys leak into logs, evidence or the repo. | Information disclosure | Keys go only to git-ignored `.showcase/keys.env`; scripts never echo them; gitleaks runs in CI. | `test_personas.py::test_setup_script_never_echoes_keys`; gitleaks job. |
| T3 | The operator key is used where a narrower persona should be. | Elevation of privilege | Each journey step uses its own persona key; `m0.sh` checks the scopes of each key first. | `m0.sh` step guard; `test_personas.py::test_scopes_are_minimal`. |
| T4 | `refco-source` is reachable from the LAN with a default password. | Elevation of privilege | Bound to `127.0.0.1`; password from the environment. | `test_compose.py::test_no_port_on_all_interfaces`. |
| T5 | Non-deterministic data hides a regression in later sprints. | Repudiation | Seeded generators and a checked manifest hash. | `test_refco_determinism.py`. |

## Abuse cases
- A test author copies a real customer list into the fixtures. The deny list and the reserved-domain check fail the build.
- The showcase script is run against a hosted stack with the operator key. The script refuses unless `MODE=local`.

## OWASP items in scope
- LLM02 2026 (sensitive information disclosure): the fixtures hold no real PII, so later leakage tests use safe data.
- Other ASI items: none. No agent behaviour changes.

## Residual risks
- A generated name can match a real person by chance. It is not linked to any real data.
- The deny list is not complete. It covers the common brands and domains.
