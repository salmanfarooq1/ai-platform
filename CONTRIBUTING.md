# Contributing

For anyone who changes the code or the docs. It covers branches and commits, tests, the checks to run, and which docs to update with a change. Local setup is in [docs/getting-started.md](docs/getting-started.md).

## Branches and commits
- **Branches.** Work happens on a branch named `sprint/NNN-slug`, created from the branch it builds on. Nothing is committed directly to `main`.
- **Commit messages** follow Conventional Commits with a scope: `type(scope): summary`. Types are `feat`, `fix`, `refactor`, `test`, `docs` and `chore`. Scopes are `api`, `ui`, `core`, `jobs`, `trust`, `sandbox`, `events`, `adr`, `design`, `planning` and `docs`.
- **Grouping.** Group commits by area (code, tests, UI, docs), not as one large commit.
- **Pull requests** use `.github/pull_request_template.md`.

## Tests
- **Coverage.** New behaviour needs a test, and a bug fix needs a regression test that fails without the fix.
- **Tiers** are pytest markers:
  - `unit`: isolated, no services
  - `integration`: real Postgres and Redis
  - `e2e`: the full app over HTTP
  - `tests/contracts/`: one suite per port, run against every adapter of that port
- **No real providers.** Models and embeddings are always fakes in tests, and the network is blocked.
- **Skips.** Only the live-MinIO contract tests may skip. `scripts/check_skips.py --expect 10` fails CI on any other skip. A check that needs a live external service belongs in `scripts/verify/`, not in a skipped test.
- **Never** weaken, skip or delete a test to make a change pass.
- **UI.** Vitest covers components, and Playwright covers flows against a real API with fake models. Axe checks accessibility in both themes.

## Checks before a pull request

```bash
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/verify scripts/eval scripts/docs
poetry run mypy
bash scripts/check_no_ddl.sh
poetry run pytest -q && poetry run python scripts/check_skips.py --expect 10
poetry run python scripts/docs/generate.py --check
cd ui && npm run tokens:check && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build && npx playwright test
```

CI runs the same checks, plus the eval gate and a migration check on an empty database.

## Docs in step with the code

| If you change | Also update |
|---|---|
| A setting | Its `description` in `core/settings.py`, then run `scripts/docs/generate.py` |
| A route or a response | `poetry run python scripts/update_openapi.py`, then `npm run gen:api` in `ui/`, and the route table in [docs/api/README.md](docs/api/README.md) |
| A reason code or event type | `gateway/reasons.py` or `ports/events.py`, then `scripts/docs/generate.py` |
| The schema | A new migration, and the migration table in [docs/deployment.md](docs/deployment.md#migrations) |
| How the system works | [docs/architecture.md](docs/architecture.md) |
| A cross-cutting decision | A new ADR in `docs/adr/`. To change a decision, write a new ADR and mark the old one superseded |
| Running or operating it | [docs/operations.md](docs/operations.md) or [docs/deployment.md](docs/deployment.md) |
| Anything users notice | [CHANGELOG.md](CHANGELOG.md), under Unreleased |
| The UI | `docs/design/` and the design skill rules |

Tests fail when a generated reference table is out of date or when a doc links to a file that does not exist.

## Writing docs
- **Tense.** Present tense: say what the system does.
- **Content.** No build history, sprint numbers or to-do lists in product docs. Planning lives in `planning/`.
- **One place.** Each topic lives in one file, and other files link to it.
- **Sentences.** Short and simple. Name things the way a reader knows them.
- **Accuracy.** Run every command you document.
