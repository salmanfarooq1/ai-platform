# Commit plan

A human runs these. No model runs `git commit` or `git push`.

Sprints 000-004 are committed and pushed on `main` (`d193878`).

## How the per-sprint blocks work
Sprints 005-010 are built one after another in the same working tree. At the end of each sprint, the Architect saves that sprint's exact file state as a git **tree object**, with `git add -A`, `git write-tree` and `git reset`. That is not a commit, and no ref is created.

Each block below uses `git restore --source=<tree> --staged -- <paths>`. It sets only the **index** to that sprint's state, and your working files are never touched. So each sprint's commits hold exactly that sprint's state, even though later sprints already changed the files.

The tree ids live only in this container's `.git`. Run the blocks in this cloud session, in order. Each branch starts from the previous sprint's branch.

## Sprint 005: frontend foundation and showcase
Tree `0e1513ea9a8199b9004d8d8f852b37f22b073635`

```bash
git switch sprint/005-frontend-foundation
```

```bash
git restore --source=0e1513ea9a8199b9004d8d8f852b37f22b073635 --staged -- .claude/skills/governed-design planning/ROADMAP.md planning/STATE.md planning/DECISIONS.md planning/QUESTIONS.md planning/RISKS.md planning/sprints/005-ports-adapters planning/sprints/006-ports-adapters planning/sprints/007-durable-jobs planning/sprints/008-trust-baseline planning/sprints/009-sandboxed-agents planning/sprints/010-kafka-event-bus
git commit -m "docs: project design skill and revised roadmap with frontend-first sprints"
```

```bash
git restore --source=0e1513ea9a8199b9004d8d8f852b37f22b073635 --staged -- api core gateway migrations scripts/admin scripts/e2e tests docs/openapi.json docs/adr .env.example .gitignore
git commit -m "feat: web-edge cookie session and read-only console API under audit:read"
```

```bash
git restore --source=0e1513ea9a8199b9004d8d8f852b37f22b073635 --staged -- ui scripts/verify .github/workflows/frontend.yml render.yaml
git commit -m "feat: TypeScript UI with governance console, workspace and showcase landing page"
```

```bash
git restore --source=0e1513ea9a8199b9004d8d8f852b37f22b073635 --staged -- .
git commit -m "docs: Sprint 005 guidelines, report and evidence"
git diff --quiet 0e1513ea9a8199b9004d8d8f852b37f22b073635 HEAD && echo "branch matches the Sprint 005 snapshot"
```

```bash
poetry run pytest -q && (cd ui && npm run lint && npx tsc --noEmit && npm test -- --run && npx playwright test)
```
This test run checks the working tree, which may already hold later sprints. To test exactly Sprint 005, first check it out alone with `git stash -u && git switch sprint/005-frontend-foundation`, run the tests, then `git stash pop`.

```bash
git push -u origin sprint/005-frontend-foundation
```

## Sprint 005b: polish round
Tree `1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003`. This branch starts from `sprint/005-frontend-foundation`, so run the Sprint 005 blocks first.

```bash
git switch -c sprint/005b-polish sprint/005-frontend-foundation
```

```bash
git restore --source=1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 --staged -- planning docs/adr/0010-design-tokens-and-ink-paper-palette.md docs/adr/README.md
git commit -m "docs: Sprint 005b pack, design decisions and ADR-0010"
```

```bash
git restore --source=1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 --staged -- api gateway tests docs/openapi.json
git commit -m "feat: overview, grouped requests and plain-language reason codes API"
```

```bash
git restore --source=1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 --staged -- ui/tokens ui/scripts ui/src/styles ui/tailwind.config.ts ui/eslint.config.js ui/package.json ui/package-lock.json
git commit -m "feat: ink-and-paper design tokens in DTCG format with drift and color guards"
```

```bash
git restore --source=1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 --staged -- ui .github/workflows/frontend.yml scripts/verify
git commit -m "feat: polish round with overview, request drawer, walkthrough, command palette and new landing page"
```

```bash
git restore --source=1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 --staged -- .
git commit -m "docs: design doc set, guidelines index and Sprint 005b report"
git diff --quiet 1ded4dbfcb89cde2ddcdce1887ecf27bd8c03003 HEAD && echo "branch matches the Sprint 005b snapshot"
```

```bash
poetry run pytest -q && (cd ui && npm run tokens:check && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build && npx playwright test)
```

```bash
git push -u origin sprint/005b-polish
```

## Sprint 006: ports and adapters, event bus, agent runtime
Tree `33601cc6f40ddbcfb6ab702b3de7965126b44b6d`. This branch starts from `sprint/005b-polish`.

```bash
git switch -c sprint/006-ports-adapters sprint/005b-polish
```

```bash
git restore --source=33601cc6f40ddbcfb6ab702b3de7965126b44b6d --staged -- ports adapters
git commit -m "feat: typed ports and adapters with a registry composition root"
```

```bash
git restore --source=33601cc6f40ddbcfb6ab702b3de7965126b44b6d --staged -- api core gateway config.py migrations Dockerfile pyproject.toml poetry.lock .env.example
git commit -m "refactor: route providers through ports; embedding provenance, event bus and agent runtime"
```

```bash
git restore --source=33601cc6f40ddbcfb6ab702b3de7965126b44b6d --staged -- tests scripts .github/workflows
git commit -m "test: contract suites per port, provenance, events, runtime and a strict skip check"
```

```bash
git restore --source=33601cc6f40ddbcfb6ab702b3de7965126b44b6d --staged -- ui
git commit -m "feat(ui): agent runs show execution id and status"
```

```bash
git restore --source=33601cc6f40ddbcfb6ab702b3de7965126b44b6d --staged -- .
git commit -m "docs: ADR-0005 update, ADR-0008, ADR-0009 and the Sprint 006 report"
git diff --quiet 33601cc6f40ddbcfb6ab702b3de7965126b44b6d HEAD && echo "branch matches the Sprint 006 snapshot"
```

```bash
poetry run pytest -q && (cd ui && npm run tokens:check && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build && npx playwright test)
```

```bash
git push -u origin sprint/006-ports-adapters
```
