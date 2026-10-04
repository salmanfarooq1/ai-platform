# Build log

## Plan
1. Poetry install, ruff baseline. 2. Mode rename + fail-fast in config and deploy files, ignore files, comments, docs, test. 3. Name removal in UI, BRANDING.md move. 4. Final checks, evidence, report.

## Log
- `poetry install --with dev` took over 2 min, ran in background; fine. Ruff baseline saved (33 errors).
- config.py: renamed mode keys, added ValueError fail-fast, replaced Koyeb comments with Render.
- Deploy/env/ignore files, code comments, README, runbook, docs/ARCHITECTURE.md updated. Added "Mode rename" to the runbook.
- `git mv` ARCHITECTURE.md and BRANDING.md into docs/. Removed section 1 (Name & Tagline) from the UI guidelines, renumbered 2-15 to 1-14, updated `§N` refs in ui/src.
- UI: brand.js, Logo, ModeBadge comment, index.html, usePageTitle, tokens.css. The Ask hero headline "Answers you can trace." was the tagline, so it became "Ask your documents."
- Added tests/unit/test_config_mode.py (3 tests pass).
- Broke: `pytest -m unit` stops at collection on tests/unit/test_llm.py (pre-existing, see QUESTIONS B1). Ran with --ignore; 3 other pre-existing failures (B2).
- npm ci + build OK.
