# Sprint 008: Builder brief

You are the Builder for Sprint 008 in `/home/user/ai-platform`. This is a vertical slice: backend first, then the UI touch. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. If you hit one, log it in `planning/QUESTIONS.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md` and `planning/STATE.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract) and `acceptance.md`.
- The Sprint 006-007 reports and the ports in `ports/` and `adapters/`. Use the EventBus, AgentRuntime and ObjectStore ports, never SDKs.
- `docs/design/` for the UI.

## Build
Everything in the blueprint. Write or append the ADR sections the blueprint names. If a container limit blocks a live check, build behind the port, add the verify script and runbook, and mark it "not verified here".

## Tests
These run on real Postgres and Redis. Cover every bullet in acceptance A2 to A7.
- **Receipts:** a valid receipt verifies offline with `scripts/verify/receipt.py`. A tampered decision, signature or chain link each fails. Two concurrent decision writes for one tenant still give one unbroken chain.
- **Retention:** the purge removes only the expired rows of the right tenant, and the chain verifies across the checkpoint.
- **Eval gate:** a mutation test that lowers a fake score makes the gate fail.
- **Cost breaker:** over the cap gives 429 `cost_cap_exceeded` with a deny row. With Redis down, the call is denied.
- **Playwright and axe:** cover A7.
- **Baseline (end of Sprint 007):** 1188 backend tests with 10 skips, all live MinIO. Also 182 Vitest and 72 Playwright tests. Keep them all green. `scripts/check_skips.py --expect 10` must pass: no new skips.

## Run
If Postgres, Redis or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d postgres redis`.

Run:
- `poetry run ruff check api core gateway ports adapters workers tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- the full pytest suite, and `scripts/check_skips.py --expect 10`

Then in `ui/`: `npm run tokens:check`, lint, tsc, `npm test -- --run`, `npm run build`, `npx playwright test`. Never run `playwright install`.

## Notes from the Architect
- **Decision writes:** the decision write still fails closed. If the chain step fails on an allow, that is 503 `decision_unrecorded`. A deny keeps its row.
- **Input text:** the chain and receipt never contain input text, only the input SHA-256 already on the row.
- **Purge:** `gap_app` has no DELETE on `gateway_decisions`, so run the purge through a narrow `SECURITY DEFINER` function with a pinned `search_path`, revoked from PUBLIC (the 0008 pattern).
- **Purge visibility:** the purge writes its checkpoint and an outbox event in the same transaction.
- **Migration:** new migration `0009`. Do not edit `0001` to `0008`.
- **Docs:**
  - Update `planning/FRONTEND_STATE.md` (the Trust row), `docs/design/CONTENT_STYLE.md`, ARCHITECTURE, README, `.env.example`, the OpenAPI snapshot, CHANGELOG and STATE.
  - Write ADR-0012 for receipts and the hash chain.
  - Record the 90-day default in `planning/DECISIONS.md`.

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
