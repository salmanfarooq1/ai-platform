# Getting started

For a developer who is new to the repository. It covers running the platform locally, making a first allowed and a first denied call, opening the console and running the tests.

## Prerequisites
- Python 3.11 and Poetry
- Docker with Compose. On Windows, use Docker Desktop with the WSL 2 backend.
- Node 22 and npm, for the UI
- For answers from a model: either Ollama running locally (the `local` mode default for embeddings is `ollama/nomic-embed-text`) or a provider key. [configuration.md](configuration.md) lists the model settings.

## 1. Install and start the stores

```bash
poetry install --with dev
docker compose up -d postgres redis
bash scripts/setup_db.sh
```

`setup_db.sh` creates the `rag_platform` database, makes sure the app role `gap_app` exists, and applies every migration as the owner role. It prints `SETUP_DONE` at the end.

## 2. Create a tenant, a principal and a key

```bash
I="poetry run python scripts/admin/identity.py"
$I create-tenant acme                                  # also creates the knowledge base `default`
$I create-kb acme legal --description "Legal documents"
$I create-principal acme service me                    # prints the principal id
$I create-key <principal-id> --scopes query kb:read kb:write agent audit:read
export GAP_KEY=<the key printed above>
```

The key is printed once. Only its hash is stored. The scopes are explained in [api/README.md](api/README.md#scopes).

Give the tenant a policy that allows only the `default` knowledge base:

```bash
echo '{"allowed_kbs": ["default"], "allowed_tools": "*", "allowed_models": "*"}' > policy.json
$I set-policy acme policy.json
$I show-policy acme
```

## 3. Run the API and a worker

```bash
poetry run uvicorn api.main:app --reload       # API on http://localhost:8000, OpenAPI docs at /docs
poetry run python -m workers                   # in a second terminal
```

Ingestion and agent runs are jobs, and the worker runs them. It also relays events. [deployment.md](deployment.md#workers) describes the other ways to run workers.

## 4. Make a first allowed and a first denied call

```bash
curl localhost:8000/health
curl -H "Authorization: Bearer $GAP_KEY" "localhost:8000/v1/documents?namespace=default"
curl -X POST -H "Authorization: Bearer $GAP_KEY" -H 'Content-Type: application/json' \
     -d '{"query": "retention rules", "namespace": "legal"}' localhost:8000/v1/search
curl -H "Authorization: Bearer $GAP_KEY" "localhost:8000/v1/decisions?limit=5"
```

What you see:
- `/health` answers without a key. `embedding` shows an error until a model is reachable. That does not stop the rest.
- The documents call is allowed: `200` and `{"documents": [], "count": 0}`.
- The search is denied by the policy, before any model is called: `403` with `{"error": {"code": "policy_denied", "message": "Denied by policy (reason: kb_not_allowed)", "request_id": "..."}}`.
- `/v1/decisions` lists both decisions. Each has the action, the resource, the outcome, the reason and the policy version.

## 5. Add a document and ask a question

This step needs a reachable embedding model and a completion model.

```bash
curl -X POST -H "Authorization: Bearer $GAP_KEY" -F "file=@policy.md" "localhost:8000/v1/ingest?namespace=default"
curl -H "Authorization: Bearer $GAP_KEY" localhost:8000/v1/jobs/<job_id>
curl -X POST -H "Authorization: Bearer $GAP_KEY" -H 'Content-Type: application/json' \
     -d '{"query": "How long are records kept?", "namespace": "default"}' localhost:8000/v1/search
```

Ingest answers `202` with a job id. The job reaches `succeeded` once the worker has chunked and embedded the file.

## 6. Open the console

```bash
cd ui && npm ci && npm run dev                 # http://localhost:5173
```

Vite forwards `/v1` to the API on port 8000. Open the workspace and sign in with the key. The governance screens (Overview, Requests, Decisions, Policies, Keys, Usage, Agent runs, Trust) need the `audit:read` scope.

## 7. Run the checks

```bash
poetry run ruff check api core gateway ports adapters workers sandbox_agent tests scripts/e2e scripts/verify scripts/eval scripts/docs
poetry run mypy
bash scripts/check_no_ddl.sh
poetry run pytest -q                           # needs the Postgres and Redis from step 1
cd ui && npm run tokens:check && npm run lint && npx tsc --noEmit && npm test -- --run && npm run build
cd ui && npx playwright test                   # starts its own API with test models; run `npx playwright install chromium` once first
```

Tests never call a real model: models and embeddings are replaced with fakes. Some contract tests need a live MinIO and are skipped without one. [CONTRIBUTING.md](../CONTRIBUTING.md) explains the test tiers.

## Next
- How the parts fit: [architecture.md](architecture.md)
- Every setting: [configuration.md](configuration.md)
- Routes, errors and reason codes: [api/README.md](api/README.md)
