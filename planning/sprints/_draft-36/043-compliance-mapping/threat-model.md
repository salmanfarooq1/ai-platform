# Sprint 043: Threat model
## Assets
- The mapping files and the coverage result. A reader trusts them as a statement of what is tested.
- System cards, model cards and the ML-BOM in packs.
- Uploaded assessments (may hold sensitive business text).
- Raw red-team reports (hold attack prompts).

## Trust boundaries crossed
- Repository files to a generated API answer.
- Admin upload to the object store.
- The red-team tools to the local API; the date check to EUR-Lex (manual run only).

## Threats (STRIDE)
| # | Threat | Category | Mitigation | Test |
|---|---|---|---|---|
| T1 | A row claims a control backed by a deleted or skipped test | Repudiation | The coverage check needs a collected test that passed in the same run | `test_check_mappings_fails_on_missing_test`, `test_check_mappings_fails_on_failed_test` |
| T2 | A model card states a digest that is not the running model | Tampering | Digest read from `models.lock`; test compares | `test_model_card_digest_matches_lock` |
| T3 | ML-BOM accepted while malformed | Tampering | CycloneDX 1.6 schema validation | `test_ml_bom_validates` |
| T4 | Another tenant's assessment or system card read | Information disclosure | RLS; same 404; object key under tenant prefix | `test_assessment_cross_tenant_404`, `test_system_card_cross_tenant_404` |
| T5 | An oversized or active file uploaded as an assessment | Denial of service / Tampering | Size cap, allowed types (PDF, Markdown, JSON), served as a download only | `test_assessment_upload_limits` |
| T6 | Red-team prompts leak into packs | Information disclosure | Summary holds counts and hashes only | `test_redteam_summary_has_no_prompts` |
| T7 | UI or docs claim "compliant" | Repudiation | `copy-check` bans the claim; page says "mapped to" | `copy-check` rule `no-compliance-claim` |
| T8 | Stale legal dates mislead an operator | Repudiation | Date file with CELEX source; doc test | `test_eu_ai_act_dates_match_source` |
| T9 | Red-team tools pull torch and hosted-model SDKs into the platform image, or skip the licence gate | Tampering | Separate venv or container outside the main lock; pinned versions; reviewed licence override file | `test_redteam_tools_not_in_main_lock`, `test_licence_overrides_reviewed` |

## Abuse cases
- A contributor deletes a flaky guardrail test. The ASI row it backed turns into a gap and the check fails.
- An admin uploads a script named `.pdf`. The type check refuses it.

## OWASP items in scope
- All of ASI01–ASI10 and LLM01–LLM10 are mapped here. This sprint only collects tests; the controls come from earlier sprints.
- LLM09 Misinformation: no overclaiming in the page, docs or cards.

## Residual risks
- A mapping row can name a test that does not really prove the control. Rows are reviewed by QA; the check only proves the test exists and passed.
- The red-team run is not in the default CI. A release without it says so in the pack.
- The EUR-Lex check needs network and a human to read the result.
