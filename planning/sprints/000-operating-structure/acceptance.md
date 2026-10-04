# Sprint 000: Acceptance

Evidence goes in `evidence/`. The Architect ticks a box only after re-running its check.

- [x] **A1.** Every file listed in AGENTS.md "Repo map → operating files" exists.
  - Check: `ls` each file.
- [x] **A2.** No old product name outside `data/` and `benchmarks/`.
  - Check: `grep -rIni verity --exclude-dir={node_modules,.git,dist,data,benchmarks} .` prints nothing.
  - Evidence: `grep-name.txt`
- [x] **A3.** No "demo" in runtime config or code.
  - Check: `grep -rIn demo config.py render.yaml docker-compose.prod.yml .env.example Dockerfile api core ui/src ui/index.html` prints nothing.
  - Evidence: `grep-demo.txt`
- [x] **A4.** An unknown `MODE` fails fast, and `public-preview` turns the reranker off.
  - Check: `tests/unit/test_config_mode.py` passes.
  - Evidence: `pytest-unit.txt`
- [ ] **A5.** *(Not met: 66 tests pass. The 3 failures and the `test_llm.py` collection error are also on `main` (checked on a clean copy), not caused by this sprint. They are fixed in Sprint 002, Q B1/B2.)* All unit tests pass.
  - Check: `poetry run pytest -m unit -q`
  - Evidence: `pytest-unit.txt`
- [x] **A6.** No new lint errors compared with the baseline.
  - Check: compare `ruff-before.txt` with `ruff-after.txt`.
- [x] **A7.** The UI builds.
  - Check: `cd ui && npm run build`
  - Evidence: `ui-build.txt`
- [x] **A8.** `.env.demo`, `.env.public-preview` and `.env.local` are ignored, and `.env.example` is not.
  - Evidence: `gitignore-check.txt`
- [x] **A9.** No secrets in the diff.
  - Check: `git diff | grep -iE "api_key|secret|password=" ` shows only placeholders.
- [x] **A10.** Docs updated: the deployment runbook has the "Mode rename" step, and links to the moved files work.
- [x] **A11.** `planning/STATE.md` and `CHANGELOG.md` are updated.

## Architect sign-off
I re-ran A2–A8 myself.
- **A5:** QA marked it pass, but it is a fail. The failures were there before this sprint, but a failing suite is not a pass.
- **A11:** QA marked it fail because of the dates. The finding is rejected. `DECISIONS.md` and `CHANGELOG.md` are dated logs, as the spec requires, and the dates rule applies to plans. `AGENTS.md` now says so.
- **Fixes I made after the build:**
  - In `pyproject.toml` and `api/routers/search.py`, the comments now say `public-preview` instead of "demo" and drop the "Koyeb" host name.
  - The Ask page subtitle no longer repeats its headline.
