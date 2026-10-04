# Sprint 000 Builder report

## 1. Criteria (builder scope)
- A2 no old name: done. `evidence/grep-name.txt` (only "severity" in scripts/corpus remains; planning/ excluded, see decisions).
- A3 no "demo" in runtime config/code: done. `evidence/grep-demo.txt` is empty.
- A4 fail-fast and reranker flag test: done. `evidence/pytest-unit.txt`.
- A5 all unit tests pass: NOT done. 1 collection error and 3 failures, all pre-existing and unrelated (QUESTIONS B1, B2).
- A6 no new lint errors: done. 33 before, 33 after, same locations. `evidence/ruff-before.txt`, `ruff-after.txt`.
- A7 UI builds: done. `evidence/ui-build.txt`.
- A8 ignore rules: done. `evidence/gitignore-check.txt`.
- A9 no secrets in diff: done, only placeholders (`GROQ_API_KEY` names).
- A10 docs: done (Mode rename section, links to moved files fixed in README).

## 2. Files changed
config.py, render.yaml, docker-compose.prod.yml, .env.example, .gitignore, .dockerignore, Dockerfile, core/database/pool.py, api/services/retriever.py, api/models/schemas.py, README.md, docs/render-deployment.md, docs/ARCHITECTURE.md (moved), docs/UI_GUIDELINES.md (moved from BRANDING.md), tests/unit/test_config_mode.py (new), ui/index.html, ui/src/brand.js, ui/src/pages/Ask.jsx, ui/src/components/layout/Logo.jsx, Logo.module.css, ModeBadge.jsx, ui/src/hooks/usePageTitle.js, ui/src/styles/tokens.css, plus comment-only BRANDING.md reference updates in about 25 other files under ui/src.

## 3. Numbers
Unit: 66 passed, 3 failed, 1 collection error (test_llm.py ignored), 2 deselected. New tests: 3 pass. Ruff: 33 before, 33 after. UI build OK.

## 4. Problems
- Poetry install exceeded the tool timeout; ran in background.
- Pre-existing test failures, left alone.

## 5. Skipped
Nothing from the brief. Out-of-scope items logged in planning/QUESTIONS.md (B1-B4).

## 6. Decisions
- Removed UI guidelines section 1 and renumbered, updating `§N` refs.
- Ask hero headline was the tagline text; changed to "Ask your documents."
- Replaced `.env`-type lines in `.dockerignore` as in the brief, so `.env.example` is no longer excluded from the Docker context.
- Left historical "Koyeb" text in docs/ARCHITECTURE.md Decision 23.
- grep-name.txt excludes planning/, which quotes the word in the briefs.
- Left "Koyeb" in api/routers/search.py and "demo" in pyproject.toml comments (not in brief).

## 7. Proposed commit commands (not run)
```
git add config.py render.yaml docker-compose.prod.yml .env.example .gitignore .dockerignore Dockerfile core api README.md docs tests ui
git add -u
git commit -m "Rename demo mode to public-preview, add MODE fail-fast, remove product name"
```
