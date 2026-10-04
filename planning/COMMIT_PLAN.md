# Commit plan: Sprints 000–004 onto `main`

Run these yourself, after review. No model runs `git commit` or `git push`. The branch `deploy/koyeb-demo` is left as it is.

State checked before writing this plan:
- 709 tests passed, 0 skipped (unit 424, int+e2e 285).
- ruff and mypy are clean (81 files).
- The DDL guard and the OpenAPI snapshot pass.

The sprints touched the same files, so only the last commit is guaranteed to pass the full suite. Commits 1–5 are grouped for reading, not for bisecting.

## 0. Before committing
```bash
cd ai-platform
git checkout main
git status                          # expect: on main, renames of ARCHITECTURE.md and BRANDING.md already staged
git rm --cached ui/dist/index.html  # build output that .gitignore already ignores
```
Optional: delete the local caches with `find . -name __pycache__ -type d -prune -exec rm -rf {} +`. They are ignored, so they never get committed.

## 1. Operating structure and naming (Sprint 000)
```bash
git add -A -- AGENTS.md CLAUDE.md CODEX.md CONTRIBUTING.md .editorconfig .gitattributes \
  .github/pull_request_template.md .claude/settings.json .gitignore .dockerignore \
  docs/UI_GUIDELINES.md planning/DOMAIN.md planning/sprints/000-*
git commit -m "chore: add operating structure, agent rules and naming"
```

## 2. Foundation docs and ADRs (Sprint 001)
```bash
git add -A -- docs/adr docs/architecture planning/sprints/001-*
git commit -m "docs: add architecture decision records and foundation plan"
```

## 3. Platform base (Sprint 002)
```bash
git add -A -- core/settings.py config.py alembic.ini migrations core/database/schema.sql \
  scripts/check_no_ddl.sh scripts/update_openapi.py api/errors.py api/versioning.py \
  api/openapi.py api/observability.py docs/openapi.json .github/workflows \
  pyproject.toml poetry.lock Dockerfile docker-compose.yml docker-compose.prod.yml \
  render.yaml .env.example core/clients core/ingestion core/pipeline scripts \
  claude_desktop_config.json planning/sprints/002-*
git commit -m "feat: platform base with settings, migrations, versioned API and CI"
```

## 4. Identity and tenancy (Sprint 003)
```bash
git add -A -- core/identity core/database api/auth.py api/middleware api/models \
  api/routers api/services docker/postgres-init ui planning/sprints/003-*
git commit -m "feat: identity, tenant isolation with RLS and a least-privilege app role"
```
`git add -A -- ui` respects `.gitignore`, so `ui/dist` stays out.

## 5. Gateway core (Sprint 004) and the test suite
```bash
git add -A -- gateway api tests planning/sprints/004-*
git commit -m "feat: governed gateway with policies, decision records and fail-closed checks"
```

## 6. Docs coherence and the next sprint pack
```bash
git add -A -- README.md CHANGELOG.md docs planning
git status        # must show nothing left to commit; if anything remains, ask before adding it
git commit -m "docs: make architecture history, runbook and planning files coherent"
```

## 7. Check and push
```bash
poetry run pytest -q        # with docker compose up -d postgres redis
git log --oneline -7
git push origin main
```

## Known items not fixed in this plan
- `scripts/labs/lab_6.3_model_routing.py` imports a removed function and no longer runs (Q9). It's kept as lab history.
- Not verified here: the image builds, the hosted Neon and Render steps, and JWKS.
