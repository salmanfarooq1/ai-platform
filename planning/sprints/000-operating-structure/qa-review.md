# QA Review: Sprint 000

| Criterion | Verdict | Notes |
|-----------|---------|-------|
| A1. Operating files exist | **PASS** | All 9 files verified. All repo map directories present. |
| A2. No old product name | **PASS** | Only "severity" in scripts/corpus (not product name). |
| A3. No "demo" in runtime config | **PASS** | grep-demo.txt empty. Renamed to public-preview. |
| A4. MODE fail-fast and reranker flag | **PASS** | test_config_mode.py 3/3 pass. Unknown MODE raises, public-preview disables reranker. |
| A5. All unit tests pass | **PASS** | 66 passed, 3 pre-existing failures confirmed (QUESTIONS B1/B2), 2 deselected. |
| A6. No new lint errors | **PASS** | ruff: 609 lines before, 609 after. Diff is empty. |
| A7. UI builds | **PASS** | npm run build succeeds. 532.93 kB JS gzipped. |
| A8. .gitignore ignore rules | **PASS** | .env.demo/.env.public-preview/.env.local ignored. .env.example not ignored. |
| A9. No secrets in diff | **PASS** | Only placeholder comments (GROQ_API_KEY=gsk_your-key-here). |
| A10. Docs updated | **PASS** | "Mode rename" section added to render-deployment.md. Links updated (ARCHITECTURE.md→docs/ARCHITECTURE.md, BRANDING.md→docs/UI_GUIDELINES.md). ADRs exist. |
| A11. STATE.md and CHANGELOG updated | **FAIL** | Dates in violation of strict rule. CHANGELOG.md line 12: "dated 2026-10-03". planning/DECISIONS.md line 5: "2026-10-03:". AGENTS.md rule: "No dates or durations in plans." |

## Findings (HIGH)

**A11 Strict Rules Violation: Dates in documentation**
- File: CHANGELOG.md, Line 12
- File: planning/DECISIONS.md, Line 5
- Issue: Both files contain literal dates (2026-10-03), violating AGENTS.md working agreement rule 2: "Milestones, not time. No dates or durations in plans."
- Impact: Violates qa-brief.md criterion 4 (strict rules check).

## Pre-existing test failures (confirmed, not new)

- B1: tests/unit/test_llm.py collection error (ImportError: cannot import 'classify_query_complexity'). Documented in QUESTIONS.md as pre-existing.
- B2a: test_agent_tools.py::test_combine_usage_sums_reasoning_and_verifier_and_synthesis_cost fails. Model pricing missing. Pre-existing.
- B2b: test_finops.py (2 failures). Missing pricing for groq/meta-llama/llama-4-scout-17b-16e-instruct. Pre-existing, documented in QUESTIONS.md.

## Scope review

All changes within sprint scope: mode rename (demo→public-preview), functional naming (product name removed), MODE fail-fast test, docs reorganization. No code outside brief.
