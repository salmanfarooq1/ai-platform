# Sprint 000: Operating structure

## Goal
Planning, building and review run through files in the repo. The platform has a functional name and no "demo" wording.

## Why
Work done by several models needs one written source of truth. A brand name on the platform itself, or a mode called "demo", is wrong for a platform meant for real use.

## Scope
- The operating files: `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.editorconfig`, `.gitattributes`, the PR template, `.claude/settings.json`, the `planning/` files, and the `docs/` ADR index and template. The Architect writes these.
- Rename the mode `demo` to `public-preview` in config, deployment files, docs and UI. Add a fail-fast check for unknown modes. The Builder does this.
- Remove the old product name from code, config, docs and UI. Move `BRANDING.md` to `docs/UI_GUIDELINES.md` and `ARCHITECTURE.md` to `docs/ARCHITECTURE.md`. The Builder does this.

## Out of scope
- Fixing the 33 lint errors that already exist.
- Any feature or behaviour change beyond the fail-fast mode check.
- `scripts/labs/`, `data/` and `benchmarks/`.

## Rules that apply
- No secrets.
- No commits.
- The live preview must keep running. The hosted service needs `MODE=public-preview` set before or with the next deploy.

## Edge cases
- A host still on `MODE=demo` must fail at startup with a clear message. It must not silently run with local defaults.
- `.env.*` files stay ignored by git under both their old and new names.

## Open questions
See `planning/QUESTIONS.md`, items Q1–Q3.
