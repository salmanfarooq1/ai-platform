# Contributing

## Git
- Create one branch per sprint, from `main`, named `sprint/NNN-slug`. Nothing goes directly to `main`.
- Use Conventional Commits: `feat(scope): …`, `fix`, `docs`, `test`, `chore`, `refactor`.
- Models propose commits and a human runs them. Group them logically (structure, docs, code, tests), not as one big commit.
```bash
git checkout -b sprint/001-foundation-architecture
git add docs/architecture/FOUNDATION.md docs/adr/
git commit -m "docs(architecture): foundation plan, strict rules and ADRs 0001-0005"
```

## Pull requests
Use `.github/pull_request_template.md`. Its sections are Sprint, What changed, Decisions, Checklist and Known limitations.

## Tests
- New behaviour needs a test. A bug fix needs a regression test.
- Fake external services (LLM, embeddings) in tests.
- Postgres integration tests run against a container and skip cleanly when Docker is unavailable.
- CI runs lint, typecheck and tests on every PR. An eval regression gate comes later.

## Walking skeleton
- Build the smallest correct path.
- Name what is deferred, and keep the deferred cost bounded: nothing that grows with usage.
- Leave a seam, such as an interface or a config switch.
- Correctness within the stated scope is never deferred.

## Docs in lockstep
| If you touch | Update |
|---|---|
| Schema | A migration, and the data section of `docs/ARCHITECTURE.md` |
| Public API | OpenAPI and `docs/ARCHITECTURE.md` |
| A strict rule or cross-cutting pattern | An ADR in `docs/adr/` |
| Commands or setup | `AGENTS.md` and `README.md` |
| Anything finished | `planning/STATE.md` and `CHANGELOG.md` |
