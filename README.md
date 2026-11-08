# Governed Agent Platform

A backend and console that put AI agents behind one governed gateway. Every call an agent or a person makes to a model, a tool or a knowledge base goes through the same checks, and every call leaves a signed record of what was decided and why.

It is for the people accountable for AI agents (team leads, owners, risk owners) and the engineers who run them.

## What it does
- **One gateway for every call.** The gateway checks the caller, the tenant's policy, input guardrails, the rate limit, the token budget and a daily cost cap, in that order. If any check cannot run, the call is denied.
- **A record of every decision.** Each call writes a decision record with the verdict, the reason, the policy version and a SHA-256 of the input. The input text is never stored. Records form a hash chain per tenant and can be verified as signed receipts.
- **Tenant isolation in the database.** Postgres row-level security keeps tenants apart. The tenant always comes from the credential.
- **Governed answers and agents.** Hybrid search over documents (keyword search with Postgres full-text ranking and vector similarity) and a LangGraph agent that checks its own answers. Both act only through the gateway. Agent runs can execute inside an OpenShell sandbox.
- **Durable work.** Ingestion and agent runs are jobs on a Postgres queue, run by workers. Events go out through a transactional outbox, in-process or to Kafka.
- **A console and a workspace.** Overview, requests, decisions, policies, keys, usage, agent runs and trust, plus Ask, Library and History.

## Architecture

```
 browser (React console + workspace)          agents, scripts, MCP clients
              |  cookie session                         |  API key or JWT
              v                                         v
        +-------------------------- FastAPI /v1 ------------------------+
        |  auth -> routes -> gateway.enforce() -> retrieval, LLM, tools |
        |                       |  decision record + outbox row         |
        +-----------------------|---------------------------------------+
                                v
   Postgres (pgvector, RLS, jobs, outbox, decisions)    Valkey (cache, limits)
                                |
        workers: ingest, agent runs (in-process or OpenShell sandbox),
                 retention purge, outbox relay -> in-process bus or Kafka
```

The full picture is in [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
poetry install --with dev
docker compose up -d postgres valkey
scripts/setup_db.sh
poetry run uvicorn api.main:app --reload       # API on :8000
poetry run python -m workers                   # worker, in a second terminal
cd ui && npm ci && npm run dev                 # UI on :5173
```

Creating a tenant and a key, and making the first allowed and denied calls, is in [docs/getting-started.md](docs/getting-started.md).

## Documentation

| I want to | Read |
|---|---|
| Run it and make a first call | [docs/getting-started.md](docs/getting-started.md) |
| Understand how it is built | [docs/architecture.md](docs/architecture.md) and [docs/adr/](docs/adr/README.md) |
| Configure it | [docs/configuration.md](docs/configuration.md) |
| Deploy or upgrade it | [docs/deployment.md](docs/deployment.md) |
| Run, monitor and fix it | [docs/operations.md](docs/operations.md) |
| Call the API | [docs/api/README.md](docs/api/README.md) |
| Build against events or ports | [docs/contracts/README.md](docs/contracts/README.md) |
| Work on the UI | [docs/design/README.md](docs/design/README.md) |
| Report a security problem | [SECURITY.md](SECURITY.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |
| See what changed | [CHANGELOG.md](CHANGELOG.md) |

## Repository layout

```
api/            FastAPI app: routes, middleware, agent, MCP server, web edge session
gateway/        enforce() and its stages, policies, decision records, receipts and the hash chain
core/           settings, database access, identity, ingestion, metrics
ports/          typed interfaces to every external provider
adapters/       the providers behind the ports, and the registry that builds them
workers/        python -m workers: job loop, handlers, retention scheduler, outbox relay
sandbox_agent/  the program that runs inside an OpenShell sandbox
migrations/     Alembic migrations 0001 to 0010, forward only
scripts/        admin CLI, database setup, eval gate, verify scripts, docs generator
ui/             React and TypeScript console, workspace and landing page
tests/          unit, integration, e2e and contract suites
docs/           product documentation
planning/       roadmap, state, decisions, questions, risks and the build history
```
