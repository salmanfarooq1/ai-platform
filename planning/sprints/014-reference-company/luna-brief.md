# Sprint 014: Builder brief for GPT-6 Luna

Re-planned 2026-11-02: see `planning/program/sprint-map.md`.

Every launch does only the work packages named in its launch prompt.

## 0. Rules for every WP

### Role and priority
You are the Builder for the WPs named in the launch prompt. This brief wins over `AGENTS.md`, `CODEX.md`, `.agents/`, `.claude/` and any skill. `test-spec.md` gives the exact tests. `blueprint.md` gives the design. If this brief and blueprint disagree, record the conflict under "Spec questions" in `build-log.md`.

### Environment
- Work in `/home/ubuntu/ai-platform-sprints/014-reference-company`.
- Use the existing Poetry 2.3.3 environment. Do not install or add dependencies.
- Do not use Docker. The Architect runs the local stack and live script.

### Hard rules
1. No commit, push, stash, reset, checkout, switch, rebase or branch change.
2. Never skip, xfail, delete or weaken a specified test or assertion.
3. Change only files allowed by the selected launch.
4. Do not write real client data or secrets. Never print a full key.
5. Never run `playwright install` or edit `.env`.
6. The Architect runs live local checks and reviews every diff.

### Output
Append one `build-log.md` entry per WP with files changed, commands and results, changed tests, spec questions and unfinished work. Final summary: at most 10 lines.

### Design rules for every WP
- Use only a verified fixture-owned tenant. Never create a tenant.
- Keys stay in the private `.showcase/keys.env`; exclude setup state from build contexts and evidence.
- The M0 denied search uses Sprint 013 admission and must cause no model request. Compare the Ollama request count.
- Restore policy only if the head remains the journey's own version. Never delete history.

## Launch A: WP1 (personas)
Journey step: Personas exist with their own keys.

**Read.** `blueprint.md` section 1, `test-spec.md` WP1, the identity admin CLI and scope definitions, `.gitignore`, `.dockerignore` and the evidence ignore list.

**Task.** Create six persona files and `scripts/showcase/setup_personas.sh`. Reuse credentials safely, support explicit `--replace <persona>`, and never print full keys. Add `.showcase/` to the relevant ignore lists. Write tests 1.1 to 1.6 exactly as specified.

**Allowed files.** `data/reference-company/personas/*.json`, `scripts/showcase/setup_personas.sh`, `scripts/showcase/personas.py`, `.gitignore`, `.dockerignore`, the evidence ignore-list file, `tests/integration/refco/test_personas.py`, `tests/unit/refco/test_personas_files.py`, `build-log.md`.

**Done when.** Tests 1.1 to 1.6 pass. No full key appears in output or artifacts.

## Launch B: WP2 (M0 showcase)
Journey step: The M0 script runs every M0 step and prints each result.

**Read.** `blueprint.md` section 2, `test-spec.md` WP2, `scripts/e2e/serve.py`, `ui/playwright.config.ts`, `ui/e2e/modules.spec.ts`, `scripts/verify/receipt.py` and the policy version API.

**Task.** Implement `scripts/showcase/m0.sh` and policy restore helper. Deny search through the Sprint 013 admission check and assert the Ollama request count does not change. Verify the receipt offline. Run an owned Gateway-only API process and verify module state. Add an isolated M0 Playwright project. Write tests 2.1 to 2.5.

**Allowed files.** `scripts/showcase/**`, `scripts/e2e/serve.py` (reference-company seed option only), `ui/e2e/showcase-m0.spec.ts`, `ui/playwright.config.ts`, `tests/integration/refco/test_m0.py`, `tests/integration/refco/test_m0_restore.py`, `build-log.md`.

**Done when.** Tests 2.1 and 2.2 pass. Playwright passes or its exact sandbox error is logged. The Architect can run `m0.sh` against the local stack.

