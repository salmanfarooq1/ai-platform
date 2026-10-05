# Sprint 009: Builder brief

You are the Builder for Sprint 009 in `/home/user/ai-platform`. This is a vertical slice: backend first, then the UI touch. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. If you hit one, log it in `planning/QUESTIONS.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md` and `planning/STATE.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract) and `acceptance.md`.
- The Sprint 006-007 reports and the ports in `ports/` and `adapters/`. Use the EventBus, AgentRuntime and ObjectStore ports, never SDKs.
- `docs/design/` for the UI.

## Build
Everything in the blueprint. Write or append the ADR sections the blueprint names. If a container limit blocks a live check, build behind the port, add the verify script and runbook, and mark it "not verified here".

## Tests
These run on real Postgres and Redis.
- Cover A1 to A6:
  - the AgentRuntime contract on the new adapter
  - run tokens bound to one `execution_id`, with a run token rejected for another run or after expiry
  - `tool_argument_not_allowed` writing a deny row
  - `sandbox_events` RLS as `gap_app`
  - the runs API merge
  - Playwright for the timeline
- **Baseline (end of Sprint 008):** 1294 backend tests with 10 skips, all live MinIO. Also 192 Vitest and 77 Playwright tests. `scripts/check_skips.py --expect 10` must still pass, so add no new skips. A live sandbox check that can't run here belongs in `scripts/verify/openshell.sh`, not in a skipped pytest.

## Notes from the Architect
- **Facts first.**
  - Before writing the adapter, confirm that the OpenShell project, its licence, its release and its CLI or API exist. Use the network if it's allowed, and record the source URLs.
  - If you can't confirm them, do not invent a CLI or flags. Build the adapter against a small `SandboxDriver` interface of your own, with a recorded fake and a clearly marked driver stub. Log a question in QUESTIONS, and say so in ADR-0009 and the runbook.
- **Pinning:** never pull an unpinned binary. Pin the version and the checksum, or download nothing.
- **Run tokens:**
  - Only a hash of the token is stored, with a short TTL.
  - The token is never logged.
  - It can't be used on routes outside the run's boundary.
- **Event detail:** `sandbox_events.detail` is truncated and holds no secrets or input text.
- **Migration:** add new migration `0010`, and do not edit `0001` to `0009`.
- **Docs to update:** ADR-0009 (append), the runbook, ARCHITECTURE, README, `.env.example`, the OpenAPI snapshot, CHANGELOG (with a test delta), STATE and `planning/FRONTEND_STATE.md`.
- **No attribution:** no model or tool attribution in any file.

## Run
If Postgres, Redis or dockerd is down: `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d postgres redis`.

Run:
- `poetry run ruff check api core gateway ports adapters workers tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- the full pytest suite, and `scripts/check_skips.py --expect 10`

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
