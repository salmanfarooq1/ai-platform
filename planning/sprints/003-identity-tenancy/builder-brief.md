# Sprint 003: Builder brief

You are the Builder for Sprint 003 of the Governed Agent Platform (repo `/home/user/ai-platform`). You implement the whole sprint end to end.

## Read in this order
1. `AGENTS.md`  2. `planning/STATE.md`  3. `planning/sprints/003-identity-tenancy/requirements.md`  4. `blueprint.md`  5. `acceptance.md`  6. `docs/architecture/FOUNDATION.md` §3 (strict rules).

## Autonomy policy (verbatim from AGENTS.md)
Work continuously until the sprint is complete. Never pause to ask for review. Write a short plan into `build-log.md`, then start. Fix problems yourself (failing tests, imports, Docker, ports, packages). Log as you go. The only stop conditions: a change that contradicts a strict rule or the blueprint; a destructive or irreversible action; a missing secret; spending money. On a stop condition, record it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, finish the rest. Never commit or push.

## Task
Implement `blueprint.md` and make every check in `acceptance.md` pass, saving captured output to `evidence/`.

## Environment
- Linux container, Python 3.11, Poetry 2.3, Node 22. Docker daemon is running; `docker compose up -d postgres redis` gives Postgres 16 + pgvector on :5432 (`postgres/postgres`) and Redis Stack on :6379.
- If the daemon is down, start it with `dockerd > /tmp/dockerd.log 2>&1 &`.
- No LLM or embedding API keys exist. Tests must use fakes. Never call a real provider.
- Add deps with `poetry add` (main) or `poetry add --group dev`. Keep `poetry.lock` consistent.

## Hard rules
- Never weaken, skip, or delete a test to get green.
- Tests assert real values, not just status codes. Each new behaviour has a test.
- No `# type: ignore` or `noqa` without a specific code and a reason comment.
- Do not change retrieval or agent logic beyond what `/v1`, errors, settings and logging need.
- Don't touch `planning/` files other than this sprint folder, `STATE.md`, `QUESTIONS.md`.

## Finish with `report.md`
1. Acceptance: done / not done / uncertain per check, with evidence path. 2. Files changed. 3. Test numbers (e.g. "84 passed, 0 failed"). 4. Problems and fixes. 5. Skipped items and why. 6. Decisions you made and deferred costs. 7. STATE/CHANGELOG updates applied. 8. Proposed commit commands on branch `sprint/003-identity-tenancy`, grouped (migration, identity core, api auth, tenant-scoped data paths, caches, mcp, ui+deploy, tests, docs).

## Sprint-specific notes
- Security code is where shortcuts hurt most. Use `hmac.compare_digest`, never log secrets or tokens, and never return them except once from the CLI.
- The test app must connect as `gap_app`, not `postgres`. Otherwise RLS tests pass for the wrong reason (superusers bypass RLS). Prove this with one test that would fail if run as a superuser.
- Keep all Sprint 002 tests passing. Update their fixtures to authenticate. Do not loosen their assertions.
