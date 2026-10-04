# Builder brief: Sprint 000, remove the product name and the "demo" mode

You are the Builder for this sprint. Work alone, in the repo at `/home/user/ai-platform`. Finish the whole task without pausing.

## Read first
1. `planning/sprints/000-operating-structure/requirements.md`
2. `planning/sprints/000-operating-structure/acceptance.md`
3. `config.py`, `render.yaml`, `ui/src/brand.js`

## Autonomy policy
- Write a short plan into `build-log.md` (in this sprint folder) and start straight away.
- Fix problems yourself: missing packages, failing imports, build errors, environment setup.
- Log as you go. Append short entries to `build-log.md`: what you did, what broke, how you fixed it.
- Stop conditions. These are the only ones:
  1. The change would contradict a strict rule.
  2. The action is destructive or outside this sprint's scope.
  3. You need a secret you don't have.
  4. The action would cost money.
- On a stop condition, record the item in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.
- Never run `git commit` or `git push`. You may use `git mv`.

## Task
The platform has no brand name. It is the "Governed Agent Platform". The live hosted mode is called `public-preview`, never "demo".

### A. Mode rename: `demo` → `public-preview`
1. **`config.py`**
   - Replace every `"demo"` mode key and `MODE == "demo"` / `MODE != "demo"` with `"public-preview"`. Update the comments to match.
   - Remove stale "Koyeb" wording in the comments. The host is now Render.
   - Add a fail-fast check right after `MODE = os.getenv(...)`. If `MODE` is not one of `local`, `public-preview` or `prod`, raise `ValueError` with a message that lists the allowed values.
   - Why: today an unknown mode silently falls back to local defaults. A host still set to `MODE=demo` would then turn the reranker on and run out of memory.
2. **`render.yaml`:** set the `MODE` value to `public-preview` and fix the comment.
3. **`docker-compose.prod.yml`:** default `MODE=${MODE:-public-preview}` and fix the comment.
4. **`.env.example`:** change the mode list and the file-name hints to `.env.public-preview`.
5. **`.gitignore` and `.dockerignore`:**
   - Replace the individual `.env.demo` style lines with `.env` plus `.env.*` and `!.env.example`.
   - Keep any other existing lines.
   - Check with `git check-ignore -v .env.demo .env.public-preview .env.local`. All three must be ignored, and `.env.example` must not be.
6. **Comments in `Dockerfile`, `core/database/pool.py`, `api/services/retriever.py` and `api/models/schemas.py`:** replace "demo" with "public-preview" or "free-tier" as fits.
7. **Docs:**
   - `README.md` and `docs/render-deployment.md`: replace "demo" wording about the mode or deployment with `public-preview`.
   - Leave text that quotes measured numbers unchanged apart from the word.
   - Add one line to `docs/render-deployment.md` under a new heading "Mode rename". It must say that the hosted service needs `MODE=public-preview` set, either by syncing the Blueprint or in the Render dashboard, before or with the next deploy.
8. **`ARCHITECTURE.md`:**
   - Move it with `git mv ARCHITECTURE.md docs/ARCHITECTURE.md`.
   - Replace the mode wording inside it.
   - Fix any links to it. Check with `grep -rn "ARCHITECTURE.md" --include=*.md --include=*.py .`.
9. **Tests:** add `tests/unit/test_config_mode.py`, marked `@pytest.mark.unit`. Use `importlib.reload` with `monkeypatch.setenv`, and restore the module afterwards. Test that:
   - `MODE=public-preview` turns the reranker off.
   - `MODE=local` turns it on.
   - `MODE=demo` raises `ValueError`.

### B. Remove the product name
1. **`ui/src/brand.js`:**
   - `name: 'Governed Agent Platform'`.
   - Remove `tagline` and `taglineCaption`, and every use of them. `Logo.jsx` should show the name only.
   - Rename the mode key `demo` to `'public-preview'` with the label `'Public preview'`.
   - Check `ModeBadge.jsx` and anything else that reads `MODES`.
2. **`ui/index.html`:** title `Governed Agent Platform — Ask`. Use a plain functional meta description with no brand and no tagline.
3. **`ui/src/hooks/usePageTitle.js` and `ui/src/styles/tokens.css`:** remove the name from the comments.
4. **`BRANDING.md`:**
   - Move it with `git mv BRANDING.md docs/UI_GUIDELINES.md`.
   - In its content, remove the product name "Verity", the tagline and any naming or tagline sections. Keep all design rules: tokens, type, motion, layout and the rest.
   - Retitle it "UI guidelines".
   - Section numbers may change. If they do, update the `BRANDING.md §N` references in `ui/src`.
   - Replace every `BRANDING.md` reference in `ui/src` with `docs/UI_GUIDELINES.md`.
5. **Final checks.** Each of these must print nothing:
   - `grep -rIni "verity" --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=data --exclude-dir=benchmarks .`
   - `grep -rIn "demo" config.py render.yaml docker-compose.prod.yml .env.example Dockerfile api core ui/src ui/index.html`

   `data/` and `benchmarks/` hold legal text where "severity" matches. Do not touch them.

### C. Do NOT touch
- `planning/`, apart from your own `build-log.md`, `report.md` and `QUESTIONS.md` entries.
- `docs/architecture/`, `docs/adr/`, `AGENTS.md` and other root `.md` files apart from the ones named above.
- `scripts/labs/`, `data/` and `benchmarks/`.
- Any behaviour other than the mode rename and the fail-fast check.

## Environment
- Python 3.11 and Poetry 2.3. Run `poetry install --with dev` first; the virtualenv is currently missing packages.
- Node 22. In `ui/`, run `npm ci`, then `npm run build`.
- The Docker daemon is not running here, so integration tests are out of scope.
- Ruff currently reports 33 errors on `main` before you change anything. Save the baseline first with `poetry run ruff check api/ core/ tests/ > evidence/ruff-before.txt`. Do not fix unrelated lint errors. Your changes must not add new ones.

## Evidence
Save the output of each command into `planning/sprints/000-operating-structure/evidence/`:
- `ruff-before.txt`
- `ruff-after.txt`
- `pytest-unit.txt`, from `poetry run pytest -m unit -q`
- `ui-build.txt`
- `grep-name.txt` and `grep-demo.txt`, from the two final checks. Empty is fine.
- `gitignore-check.txt`

## Report
Write `planning/sprints/000-operating-structure/report.md` with these sections:
1. Each criterion: done or not done, with its evidence path.
2. Files changed.
3. Test and check numbers.
4. Problems hit and how you fixed them.
5. Items skipped.
6. Decisions you made.
7. Proposed commit commands. Do not run them.

Then finish. Your final message should be a five-line summary.
