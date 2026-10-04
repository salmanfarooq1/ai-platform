# Sprint 005: Builder brief

You are the Builder for Sprint 005 of the Governed Agent Platform (repo `/home/user/ai-platform`). You implement the whole sprint end to end.

## Read in this order
1. `AGENTS.md`  2. `planning/STATE.md`  3. `planning/sprints/005-ports-adapters/requirements.md`  4. `blueprint.md`  5. `acceptance.md`  6. `docs/architecture/FOUNDATION.md` §3 (strict rules).

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
1. Acceptance: done / not done / uncertain per check, with evidence path. 2. Files changed. 3. Test numbers (e.g. "84 passed, 0 failed"). 4. Problems and fixes. 5. Skipped items and why. 6. Decisions you made and deferred costs. 7. STATE/CHANGELOG updates applied. 8. Proposed commit commands on branch `sprint/005-ports-adapters`, grouped (ports, adapters per port, registry+wiring, migration, tests, docs).

## Sprint-specific notes
- Subagents cannot write report files. Return the full `report.md` text in your final reply, and the Architect saves it. Write evidence via shell redirection of real command output.
- This is a refactor: move code, do not change behaviour. Every existing test must pass with unchanged assertions. Only fixtures may change, to build the app from the registry.
- Fail closed means deny on any exception, including bugs in your own stages. Test it.
- Run the full suite after each port is moved, and log it in build-log.md.
