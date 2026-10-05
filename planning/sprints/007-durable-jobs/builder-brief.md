# Sprint 007: Builder brief

You are the Builder for Sprint 007 in `/home/user/ai-platform`. This is a vertical slice: backend first, then the UI touch. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. If you hit one, log it in `planning/QUESTIONS.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md` and `planning/STATE.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract) and `acceptance.md`.
- The Sprint 006 report and the ports in `ports/` and `adapters/`. Use the EventBus, AgentRuntime and ObjectStore ports, never SDKs.
- `docs/design/` for the UI.

## Build
Everything in the blueprint. Write ADR-0008 updates (an outbox section) and a short ADR note on the job queue design: Postgres SKIP LOCKED versus a broker, and why.

## Tests
These run on real Postgres and Redis. Cover every bullet in acceptance A2–A5.
- For the race test, run two workers concurrently in the same test.
- For the crash test, kill a worker mid-job and check the job is re-claimed after its lease expires.
- Add Playwright for A6.
- Keep all existing tests green: the backend baseline is in the 006 report, and the UI has 162 Vitest tests and 70 Playwright tests.

## Run
If Postgres, Redis or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d postgres redis`.

Run:
- `poetry run ruff check api core gateway ports adapters workers tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- the full pytest suite (0 skipped)

Then in `ui/`: `npm run tokens:check`, lint, tsc, `npm test -- --run`, `npm run build`, `npx playwright test`. Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests.
- No secrets.
- No commits or pushes.
- No "demo" wording.
- Simple sentences in docs.

## Finish
Write `report.md` and the evidence files. Return a text summary with:
- the acceptance table
- the test numbers
- deviations
- open questions
