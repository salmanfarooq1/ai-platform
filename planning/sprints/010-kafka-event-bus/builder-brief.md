# Sprint 010: Builder brief

You are the Builder for Sprint 010 in `/home/user/ai-platform`. This is infrastructure only: backend only, with no UI change. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. If you hit one, log it in `planning/QUESTIONS.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md` and `planning/STATE.md`.
- This folder: `requirements.md`, `blueprint.md` (the contract) and `acceptance.md`.
- The Sprint 006-007 reports and the ports in `ports/` and `adapters/`. Use the EventBus, AgentRuntime and ObjectStore ports, never SDKs.
- `docs/design/` for the UI.

## Build
Everything in the blueprint. Write or append the ADR sections the blueprint names. If a container limit blocks a live check, build behind the port, add the verify script and runbook, and mark it "not verified here".

## Tests
These run on real Postgres and Redis. Cover A1 to A5 and every test the blueprint lists:
- the contract suite
- 1,000-event ordering over 3 tenants
- a relay restart mid-batch, with no loss and no double handling after dedupe
- the poison message reaching `<topic>.dlq`
- the switch back to `outbox` with no data migration

**Baseline at the end of Sprint 009:**
- 1523 backend tests, with 10 skips, all live MinIO.
- 207 Vitest and 82 Playwright tests. The UI is unchanged in this sprint, but run its checks anyway.

`scripts/check_skips.py --expect 10` must still pass. The pytest suite uses the in-memory Kafka fake. A live Redpanda run goes in `scripts/verify/kafka.sh` and its evidence, never in a skipped pytest.

## Notes from the Architect
- **Pinning:** pin `aiokafka` exactly, and pin the Redpanda image by version. If the image can be pulled here, run `scripts/verify/kafka.sh` live and save the output.
- **The fake models real Kafka behaviour:** partitions by key hash, offsets, commit only after the handler succeeds, redelivery of uncommitted messages, and DLQ after `max_attempts`. Don't make it simpler than the contract needs.
- **The decision rule still holds:** a decision row is never lost because of the bus. Kafka is reached only by the relay, never inside the decision transaction.
- **SASL:** settings come from the environment only and are never logged. Use `SecretStr`.
- **Migrations:** add none unless one is truly needed. If one is needed, it is `0011`.
- **Docs to update:** ADR-0008 (Kafka section), `docs/runbooks/kafka.md`, ARCHITECTURE, README, `.env.example`, CHANGELOG (with a test delta), STATE, ROADMAP and QUESTIONS.
- **No model or tool attribution** in any file.

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
