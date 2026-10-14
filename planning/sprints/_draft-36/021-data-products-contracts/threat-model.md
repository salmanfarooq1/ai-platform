# Sprint 021: Threat model

## Assets
- Contract documents: they will drive checks (022), masks (024) and agent rules (032).
- Classification and sensitivity of products and columns.
- Lifecycle state and its audit trail.

## Trust boundaries crossed
- A producer's uploaded JSON or YAML enters the platform.
- `datacontract-cli` runs on that input inside the API or worker process.

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A stored contract version is edited after publish, silently weakening rules | Tampering | `gap_app` has no UPDATE on `data_contracts`; SHA-256 stored and in the decision record | `test_contract_immutable.py::test_update_denied`, `test_hash_in_record` |
| T2 | A breaking change is published as a minor to avoid review | Tampering | Server-side diff decides the minimum bump | `test_contract_diff.py::test_bump_enforced` |
| T3 | Classification lowered quietly (restricted to internal) | Tampering | Changed classification is major; needs a new output port | `test_contract_diff.py::test_classification_change_major` |
| T4 | A product with PII goes to review unclassified | Information disclosure | Every column and the product need a classification before `in_review` | `test_product_lifecycle.py::test_review_requires_classification` |
| T5 | A producer moves their own product to `certified` | Elevation of privilege | Transition table maps steward steps to `product.certify`, granted only by `data:steward` | `test_product_lifecycle.py::test_owner_cannot_certify` |
| T6 | Lifecycle change without a trace | Repudiation | `product_events` append-only, linked to a decision id | `test_product_lifecycle.py::test_event_per_transition` |
| T7 | YAML bomb or huge document | Denial of service | Safe loader, `CONTRACT_MAX_BYTES`, alias limit | `test_contract_validate.py::test_yaml_bomb_refused` |
| T8 | Search returns another tenant's products or column names | Information disclosure | RLS on all searched tables | `test_products_tenancy.py::test_search_isolated` |
| T9 | `datacontract-cli` reaches the network or S3 with platform secrets | Information disclosure | Lint and schema test through the Python API only; schema read via `QueryEngine`; network guard in tests | `test_contract_validate.py::test_no_network` |
| T10 | A JSON Schema aspect type with remote `$ref` fetches URLs | Information disclosure | Only local `#` refs allowed, as for `tool_arguments` | `test_products_api.py::test_aspect_type_remote_ref_refused` |

## Abuse cases
- A producer uploads v1.1.0 that removes the `salary` mask rule. The diff marks it major, and the upload is refused.
- A producer with `data:write` calls the certify transition. Denied by the boundary.

## OWASP items in scope
- OWASP Top 10:2025 A01 Broken Access Control (T5, T8), A08 Software and Data Integrity Failures (T1, T2).
- ASI06 Memory and Context Poisoning (early): contracts will feed agent rules later, so their integrity starts here.
- LLM Top 10: none. No model is called.

## Residual risks
- A steward can still approve a bad contract. Separation of duties is checked from 022.
- `CONTRACT_DEPRECATION_DAYS` is a placeholder until the owner confirms it.
