# AGENTS.md

These are the instructions for every model working in this repo. Read this file first.

## Project
This is the Governed Agent Platform: governed agents on business data. It is a Python modular monolith with four layers:
- **Data:** ingestion, documents, data models.
- **AI and agents:** hybrid retrieval, LangGraph agents, an MCP server.
- **Gateway:** identity, policy, guardrails, budgets and audit, behind one `enforce()` entry point.
- **Trust:** evals, cost, tracing.

The system and its strict rules are described in `docs/architecture.md`.

## Stack
- **Backend:** Python 3.11, Poetry 2.3.3, FastAPI with async `asyncpg`, Postgres 16 with pgvector, Valkey Search, LiteLLM, LangGraph, MCP.
- **Stack:** Valkey, optional Apache Kafka (`streams`), SeaweedFS (`lake`), and local or hosted models (`models`). Service security rebuilds use pinned inputs and are scanned as final artifacts.
- **UI:** Vite with React 18 and TypeScript (strict), Tailwind and shadcn/ui, TanStack Query, in `ui/`. Playwright tests are in `ui/e2e/`.
- **Modes:** the `MODE` env var is `local`, `public-preview` or `prod`.

## Repo map
| Path | What |
|---|---|
| `api/` | FastAPI app: `routers/`, `middleware/` (auth, then FinOps), `auth.py`, `gateway_deps.py`, `agent/` (LangGraph), `mcp/`, `services/`, `models/` |
| `ports/` | The contracts for every external provider: typed Protocols and frozen dataclasses. No SDK imports (ADR-0005) |
| `workers/` | Job workers (`python -m workers`): the loop, the ingest and agent-run handlers, the outbox relay, embedded workers (ADR-0011) |
| `adapters/` | The only code that imports `litellm`, `langchain_litellm`, `redis`, `boto3`, `openshell`: one adapter per port, and `registry.py`, the composition root that builds them from `Settings` |
| `gateway/` | The governance path: `enforce()`, `ExecutionBoundary`, policies, stages, rate limit and token budget, decision record (ADR-0006) |
| `core/` | Ingestion, processing, pipeline, DB pool and tenant-scoped access (`database/tenant.py`), identity (`identity/`), provider clients |
| `config.py` | All config, selected by `MODE` |
| `tests/` | `unit/`, `integration/` (pytest markers `unit`, `integration`, `e2e`) |
| `ui/` | Web UI. Design rules are in `docs/design/` (index: `docs/design/README.md`). Tokens are data: `ui/tokens/tokens.json` |
| `scripts/` | Labs (`scripts/labs/`), corpus building (`scripts/corpus/`), eval scripts (not shipped). `scripts/admin/` is the identity CLI |
| `docs/` | Product docs: `getting-started.md`, `architecture.md`, `configuration.md`, `deployment.md`, `operations.md`, `api/`, `contracts/`, `adr/`, `design/`. Generated tables: `scripts/docs/generate.py` |
| `planning/` | `MAP`, `STATE` (pointer to `MAP`), `DECISIONS`, `DOMAIN`, `RISKS`, `QUESTIONS`, `ROADMAP`, `sprints/NNN-slug/` |

Operating files: `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.editorconfig`, `.gitattributes`, `.github/pull_request_template.md`, `.claude/settings.json`.

## Commit scopes
`api`, `ui`, `db`, `core`, `adapters`, `ops`, `ci`, `adr`, `planning`, `gateway`, `evidence`, `agents`, `sandbox`, `events`, `jobs`, `models`, `lake`, `pipelines`, `cdc`, `products`, `quality`, `access`, `lineage`, `semantic`, `insights`, `documents`, `policy`, `approvals`, `identity`, `protocols`, `guardrails`, `memory`, `receipts`, `observability`, `packaging`.

## Commands
Verified in a Linux container (see `planning/QUESTIONS.md` Q1 for WSL).
```bash
poetry install --with dev                 # setup (add --with rerank for the cross-encoder)
docker compose up -d postgres valkey       # local stack (also creates the app login role gap_app; ollama is optional)
scripts/setup_db.sh                       # create rag_platform if missing, migrate as the owner role, grant gap_app
poetry run alembic upgrade head           # migrate only (runs as MIGRATION_DATABASE_URL, falls back to DATABASE_URL)
poetry run python scripts/admin/identity.py --help   # tenants, principals, API keys (the key is printed once), set-policy / show-policy
poetry run uvicorn api.main:app --reload  # run API on :8000 (product routes are under /v1)
poetry run python -m workers              # run a worker: ingestion and agent runs need one (or `docker compose up -d worker`, or EMBEDDED_WORKERS=1)
cd ui && npm ci && npm run dev            # run UI on :5173 (Vite proxies /v1 to :8000)
poetry run pytest -m unit -q              # unit tests (no external services)
poetry run pytest -m "integration or e2e" -q -rs  # real Postgres + Valkey, fake LLM; skips with a reason if they are down
poetry run ruff check api core gateway evidence ports adapters workers sandbox_agent tests scripts/e2e scripts/docs   # lint
poetry run mypy                           # typecheck (api/ core/ gateway/ evidence/ ports/ adapters/ workers/ sandbox_agent/ config.py; strict for evidence/, ports/, adapters/ and sandbox_agent/)
poetry run python scripts/update_openapi.py  # refresh docs/api/openapi.json after an intended API change (unit test fails on drift)
scripts/check_no_ddl.sh                   # no CREATE/ALTER TABLE outside migrations/
scripts/supply_chain/licence_gate.sh      # OSI licence gate (install --with supply-chain)
cd ui && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check   # UI checks
cd ui && npm run e2e                      # Playwright against the real API with fakes (needs postgres and valkey)
```
- **Typecheck:** `poetry run mypy`, configured in `pyproject.toml`. Strict for `core/settings.py`, `api/errors.py`, `api/observability.py`, `api/versioning.py`, non-strict elsewhere.
- **Schema:** Alembic only (`migrations/`, forward-only). Add a migration for any schema change; never edit `0001` or `0002`. Migrations run as the owner role (`MIGRATION_DATABASE_URL`); the app runs as `gap_app` (`DATABASE_URL`).
- **Identity and tenancy:** every `/v1` route except `/v1/health` needs `Authorization: Bearer <API key or JWT>`. The tenant comes only from the verified credential, never from a header, query or body. Every request-path query goes through `tenant_connection(pool, tenant_id)`; Postgres row-level security does the rest. The app refuses to start as a superuser or `BYPASSRLS` role, so tests and local runs use `gap_app`, never `postgres`. Scopes: `kb:read`, `kb:write`, `query`, `agent`, `audit:read`, `admin`. Browsers sign in at `POST /v1/session` and then use a `gap_session` cookie plus `X-CSRF-Token` (ADR-0007); bearer keys and JWTs work unchanged.
- **Gateway:** every model, tool and KB call goes through `gateway.enforce()` (routes `require()` it, the agent and MCP tools too); any error is a deny. A tenant narrows what it may do with a policy (`identity.py set-policy <tenant> <file.json>`); with none, scopes grant against the platform defaults. Every call writes a `gateway_decisions` row (SHA-256 of the input, never the text). A failed decision write on an allow is a deny (503 `decision_unrecorded`). Agent tools and MCP code must not import `litellm`, `langchain_litellm` or `asyncpg` (import-lint test). A table added by a migration needs an explicit `GRANT` to `gap_app`.
- **Ports and adapters:** routes, the gateway, the agent and MCP get their providers as ports from `request.app.state.adapters` (built once in the lifespan by `adapters/registry.py`), never an SDK. Provider SDKs (`litellm`, `langchain_litellm`, `boto3`, `redis`) are imported only in `adapters/`, and `asyncpg` only in `adapters/`, `core/database/` and `core/identity/store.py` (import-lint test, `tests/unit/test_import_lint_ports.py`). Routes that only need a type use `core.database.tenant.DbPool`. Chunks record `embedding_model` and `embedding_dim`; search ignores rows of another model, and `/v1/health` reports them as `stale_vectors`.
- **How to add a provider:** (1) if the port exists, write `adapters/<name>.py` implementing it, typed strictly (mypy is strict there); (2) choose it in `adapters/registry.py` from a `Settings` value, and validate that value in `core/settings.py`; (3) add the adapter to the port's contract suite in `tests/contracts/` (real and fake must pass the same tests); (4) add a fake to `tests/fakes.py` if tests need one, and give tests the app through `create_app(adapter_overrides={...})`; (5) never import the SDK anywhere else. A new kind of port goes in `ports/` first, with a contract suite, and an ADR if it is a cross-cutting decision.
- **Trust (Sprint 008, ADR-0012):** every decision row joins a per-tenant hash chain, and `GET /v1/receipts/{id}` signs it (Ed25519, `RECEIPT_SIGNING_KEY`; check offline with `scripts/verify/receipt.py`). Decision records are purged after `DECISION_RETENTION_DAYS` (90) by the `purge_decisions` job. A `cost` stage enforces a daily cost cap. `/metrics` serves Prometheus text. `scripts/eval/run_gate.py` is the CI eval gate.
- **Events and runs:** the gateway publishes `platform.gateway.decision.v1` (CloudEvents 1.0, no input text) for every recorded decision through the `EventBus` port (ADR-0008). `/v1/agent/query` runs through the `AgentRuntime` port (ADR-0009), and every decision a run causes carries its `execution_id`.
- **Sandboxed runs (Sprint 009, ADR-0009):** `AGENT_RUNTIME=openshell` makes a worker run each agent run in an OpenShell sandbox behind the `SandboxDriver` port (`ports/sandbox.py`; the SDK is imported only in `adapters/openshell_driver.py`). The sandbox's one network route is the gateway: the agent in it (`sandbox_agent/`) calls `/v1/sandbox/runs/{execution_id}/...` with a run token (bound to one run, hash stored, short-lived, valid on no other route). A policy's `tool_arguments` (a JSON Schema per tool) are checked in the policy stage (`tool_argument_not_allowed`). Sandbox events go to `sandbox_events` and are merged with the run's decisions in `GET /v1/agent/runs/{execution_id}`. Tests use `tests/fake_sandbox.py` (not a recording of a real run); `scripts/verify/openshell.sh` runs A2 to A5 on a real gateway (`docs/operations.md`).
- **Jobs and the outbox:** `POST /v1/ingest` answers 202 with a job; a worker ingests. Agent runs are jobs behind the `AgentRuntime` port (`/v1/agent/query` waits `AGENT_SYNC_WAIT_SECONDS`, then 202). Workers claim with `SKIP LOCKED` through a narrow SECURITY DEFINER function and then work under `tenant_connection`. The default event bus is the outbox: events commit with the change, a relay publishes them at least once, consumers dedupe by event id (ADR-0008, ADR-0011).
- **API:** every product route is under `/v1`. Only `/` and `/health` are unversioned. Errors are always `{"error": {"code", "message", "request_id"}}`. 401 = no or bad credential, 403 = missing scope, 404 `kb_not_found` = unknown or foreign knowledge base (same body for both).
- **Tests:** the integration and e2e tiers need `docker compose up -d postgres valkey`. They create a throwaway database, connect as `gap_app`, use fake LLM and embeddings (`tests/fakes.py`, fake adapters put behind the ports through the registry), and a guard fixture blocks any real network call. `tests/contracts/` runs one suite per port against every adapter; the live SeaweedFS run is `scripts/verify/seaweedfs.sh` (skipped, with a reason, when no live S3 endpoint is configured). The `tenants` fixture gives two tenants with keys of different scopes.

## Read order
1. `AGENTS.md`
2. `planning/MAP.md`: the North Star, the feature map, the milestones, agreed decisions and what is happening now. It wins over any older plan.
3. `planning/DECISIONS.md`
4. The active sprint pack in `planning/sprints/NNN-slug/`.

Read `planning/DOMAIN.md`, `docs/adr/` and `docs/architecture.md` when the task touches them.

## Strict rules
The 15 strict rules are in `docs/architecture.md` section 2. Never break one. If a task seems to need it, stop, and write it in `planning/QUESTIONS.md`.

## Working agreements
1. **No model runs `git commit` or `git push`.** Put the proposed commands in `report.md`, and a human runs them.
2. **Milestones, not time.** No dates or durations in plans. Log entries in `DECISIONS.md` and `CHANGELOG.md` may carry the date they were recorded. A sprint is done when its acceptance checks pass.
3. **Be concise.** Short files, plain words, specifics.
4. **No invented facts or business rules.** Write unknowns in `planning/QUESTIONS.md` and continue.
5. **Never weaken, skip or delete a test to get green.** Decide whether the code or the expectation is wrong, and say which.
6. **No secrets in the repo or in logs.** Refer to them by env var name only.
7. **No "demo" wording.** The hosted mode is `public-preview`.
8. **No brand name on the platform.** Use functional names. Names belong only to use cases built on top.
9. **Never reference any employer or employer product.** The working method is adapted from the public 120x Operators Kit.
10. **Branch per sprint:** `sprint/NNN-slug`. Nothing goes straight to `main`.

## Builder autonomy policy
The Builder works continuously until the sprint is complete. It never pauses to ask for review.
- **Finish before ending the turn.** Answer progress questions briefly while continuing the work. Do not end with a status-only reply while authorized work or checks remain. Collect long-running results and finish the report before handing off; documented hard stops still require finishing unaffected work.
- **Write the plan down, then start.** Put a short plan in `build-log.md` and begin straight away.
- **Fix problems yourself.** Failing tests, import errors, Docker or port issues, missing packages, environment setup and WSL paths are part of the job.
- **Log as you go.** Append short entries to `build-log.md`: what you did, what broke, how you fixed it.
- **Stop conditions.** These are the only ones:
  1. The change contradicts a strict rule or the blueprint.
  2. The action is destructive or irreversible, such as deleting data, dropping tables, rewriting git history, or removing files outside the sprint scope.
  3. A secret is needed that isn't available.
  4. The action would spend money.
- **On a stop condition, keep going on everything else.** Record the item in `planning/QUESTIONS.md` and `build-log.md`. Take the documented fallback if there is one, skip only that item, and finish the rest.
- **Never commit or push.** Put the proposed commit commands in `report.md`.

## Completion standard
A sprint is complete when:
- Every check in `acceptance.md` has evidence in `evidence/`. This must be captured command output, not hand-written.
- Lint, typecheck and tests pass with no new failures.
- Docs are updated in lockstep (see `CONTRIBUTING.md`).
- `planning/MAP.md` (within its size limit) and `CHANGELOG.md` are updated.
- `report.md` lists the proposed commits.
