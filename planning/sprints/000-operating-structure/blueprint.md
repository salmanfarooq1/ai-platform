# Sprint 000: Blueprint

## Files to read
`config.py`, `render.yaml`, `ui/src/brand.js`, `BRANDING.md`

## Files to create (Architect)
`AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.editorconfig`, `.gitattributes`, `.github/pull_request_template.md`, `.claude/settings.json`, `planning/*`, `docs/adr/README.md`, `docs/adr/TEMPLATE.md`.

## Files to modify (Builder)
See `builder-brief.md` §A and §B: config, deploy files, `.gitignore` and `.dockerignore`, docs, UI brand files. `git mv` `BRANDING.md` to `docs/UI_GUIDELINES.md`, and `ARCHITECTURE.md` to `docs/ARCHITECTURE.md`.

## Steps
1. The Architect writes the operating files.
2. The Builder renames the mode and removes the old name.
3. QA reviews.
4. The Architect re-runs the checks.

## Data model / API changes
- No schema change.
- `/health` now reports `"mode": "public-preview"` instead of `"demo"`.

## Test plan
- New: `tests/unit/test_config_mode.py`.
- All unit tests pass, and the UI builds.

## Walking-skeleton notes
- Settings validation is minimal: the `MODE` check only. Full pydantic-settings comes in Sprint 002.
- Seam: the single allowed-modes check in `config.py`.
