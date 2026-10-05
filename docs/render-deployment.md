# Render Deployment Runbook (MODE=public-preview)

Status: the first deploy was prepared and verified locally. Everything up to
"First-time setup" has been done and tested. Connecting the repo needs a
dashboard action only you can take. For a database that already holds data, use
the "Hosted migration checklist" at the end. Whether the hosted services are
live now is open (`planning/QUESTIONS.md` Q10).

---

## What MODE=public-preview actually requires

`config.py` selects services by `MODE`. In `public-preview` the platform needs these
variables from the environment:

| Variable | Used by | Notes |
|---|---|---|
| `GROQ_API_KEY` | A Groq model, only if `LLM_MODEL` selects one | Still prompted for in `render.yaml`. The default completion model is `gemini/gemini-3.5-flash-lite`. |
| `GEMINI_API_KEY` | Embeddings (`gemini/gemini-embedding-001`) | Verified working. |
| `DATABASE_URL` | asyncpg pool, pgvector retrieval | Neon Postgres 16 + `vector` extension. Must be the `gap_app` role, not the owner. |
| `MIGRATION_DATABASE_URL` | `alembic upgrade head` in the start command | The owner role. |
| `REDIS_URL` | Cache, rate limit, token budget | **Must have the RediSearch module.** Search, ingest and agent runs answer 503 `dependency_unavailable` while Redis is unreachable. |

Plus `MODE=public-preview` itself, and `WEB_CONCURRENCY=1` to stay inside 512MB. `PREVIEW_PRINCIPAL_ID` turns on the read-only preview session (see the checklist). The UI service needs no secret.

### Why Redis needs RediSearch

`api/main.py`'s lifespan calls `create_semantic_cache_index()`, which issues
`FT.CREATE` and re-raises anything that is not "Index already exists". On a
Redis without the RediSearch module the command is unknown, the exception
propagates out of startup, and **the app never boots**.

This rules out Upstash. Use Redis Cloud's free Essentials tier (30MB), which
ships RediSearch and JSON. `redis.from_url` accepts its `rediss://` URL as-is.

### Why the embedding model changed

Public-preview mode used to default to `ollama/nomic-embed-text`, which resolves to
`localhost:11434`. There is no Ollama sidecar on a 512MB Render instance, so
that default could never have worked in the cloud. `/health` would have
reported the embedding probe down and every search would have failed.

It now defaults to `gemini/gemini-embedding-001`. That model emits 3072 floats
natively, so `adapters/litellm_embeddings.py` (formerly `core/clients/embeddings.py`) requests 768 and renormalizes the
truncated vector, keeping the `VECTOR(768)` column from the Alembic baseline (`migrations/versions/0001_baseline.py`) unchanged.

`text-embedding-004` is retired and returns 404 on current API keys. Do not
switch back to it.

### Why Neon's pooled connection needs a pool tweak

Neon's pooled endpoint (`-pooler` in the hostname, PgBouncer in transaction
mode) doesn't support asyncpg's server-side prepared-statement cache. Every
query after the first fails. `core/database/pool.py` now passes
`statement_cache_size=0` to `asyncpg.create_pool`, which disables that cache
and works against both the pooled and direct Neon endpoints.

---

## What was changed to make this fit a 512MB free instance

The existing `FEATURES["reranker_enabled"] = MODE != "public-preview"` flag stopped the
cross-encoder from *loading*, but `api/services/retriever.py` imported
`sentence_transformers` at module scope, so **torch was imported on every
boot regardless of the flag**: roughly 300MB resident and a multi-GB image.

1. `api/services/retriever.py`: `CrossEncoder` is now imported inside
   `get_cross_encoder()`, so the flag genuinely avoids the cost.
2. `pyproject.toml`: `sentence-transformers` moved to a `rerank` dependency
   group, `matplotlib`/`deepeval` to a `labs` group.
3. `Dockerfile`: takes an `INCLUDE_RERANK` build arg, default `false`. Render
   uses the default, so the public-preview image never installs torch. A prod build
   would set `INCLUDE_RERANK=true` to get the reranker back. See Decision 20
   in `ARCHITECTURE.md`.
4. `core/clients/embeddings.py`: new. Single entry point for all three
   embedding call sites (ingestion, semantic cache, `/health` probe).
5. `/health` now reports the embedding probe as its own field instead of
   folding it silently into `status`.

### Measured result

| | Before | After (public-preview, `INCLUDE_RERANK=false`) |
|---|---|---|
| Image size | ~3GB (torch) | **119 MiB** |
| RSS after import | not measured | 268 MB |
| Steady-state container RSS | not measured | **240 MiB** / 512MB budget |

---

## Infrastructure already provisioned

### Postgres, Neon: done

Free project created at <https://neon.tech>, pgvector enabled, schema
applied (originally from `core/database/schema.sql`, now replaced by `alembic upgrade head`; on this
database the baseline migration `0001` changes no table and only records the Alembic version). Corpus ingested: **452 chunks**
in the `kyc_aml` namespace, embedded with `gemini/gemini-embedding-001` so
they match what live queries will produce. `data/compliance/real/legal/`
(GDPR, CCPA, HIPAA) exists in the repo but has not been ingested yet, so
the `legal` namespace is empty in Neon right now, not by design.

The connection string is the `postgresql://...?sslmode=require` pooled
(`-pooler`) form. See the pool-tweak note above for why that's safe here.

### Redis, Redis Cloud: done

Free database created at <https://redis.io/try-free/>. Verified:

- `MODULE LIST` includes `search` (RediSearch v80610), plus `ReJSON`, `bf`,
  `timeseries`, `vectorset`.
- The actual startup call the app makes,
  `create_semantic_cache_index()` issuing `FT.CREATE idx:semantic_cache ...
  DIM 768`, succeeds against this instance and is idempotent on a second
  call (the "Index already exists" branch), so it won't crash boot.

Neither credential is written to any file in this repo. Both go into the
Render dashboard as secrets in the step below.

### Render blueprint: done

`render.yaml` at the repo root defines the API service (Docker runtime, free
plan, `/health` health check, `MODE=public-preview`, `WEB_CONCURRENCY=1`) and the UI service
(`ai-platform-ui`). It marks `GROQ_API_KEY` / `GEMINI_API_KEY` / `DATABASE_URL` /
`MIGRATION_DATABASE_URL` / `REDIS_URL` / `PREVIEW_PRINCIPAL_ID` (API) as
`sync: false` so Render prompts for them as masked secrets instead of
reading them from the file.

---

## First-time setup

### 1. Connect the repo (dashboard action, only you can do this)

1. Push this branch (or merge to `main`) to GitHub.
2. Render dashboard → **New** → **Blueprint** → select this repo.
3. Render reads `render.yaml` and prompts for the secret env vars. Paste in the
   Groq key, Gemini key, Redis Cloud `REDIS_URL`, and the two database URLs and
   `PREVIEW_PRINCIPAL_ID` as the checklist below says.
4. Deploy. First build installs `poetry install --only main` inside Docker
   and should take a few minutes.

### 2. Verify

```bash
curl https://<service>.onrender.com/health
```

Expect `db`, `redis`, and `embedding` all `"ok"` and `"mode":"public-preview"`. Every
`/v1` route except `/v1/health` needs a key, so search needs a key with the `query` scope:

```bash
curl -X POST https://<service>.onrender.com/v1/search \
  -H "Authorization: Bearer $GAP_KEY" -H 'Content-Type: application/json' \
  -d '{"query": "customer due diligence requirements", "namespace": "kyc_aml"}'
```

Note free-tier Render instances spin down after 15 minutes idle and
cold-start on the next request. Expected on this plan, not a bug.

## Hosted migration checklist (migrations 0001 to 0007)

One ordered list for moving the hosted stack to the current head. The container start command runs
`alembic upgrade head`, so migrations that are already applied are skipped. Do the steps in order.

1. **Back up the Neon database** (a branch or a dump). Nothing here is reversible, because migrations are forward-only (`planning/QUESTIONS.md` Q4).
2. **Set `MODE=public-preview`** on the API service, by syncing the Blueprint or in the dashboard. The old value `demo` fails at startup (Q2).
3. **Create the app role on Neon**, as the owner role (`neondb_owner`), with a generated password kept out of the repo:
   ```sql
   CREATE ROLE gap_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '<generated>';
   GRANT CONNECT ON DATABASE neondb TO gap_app;   -- use your database name
   ```
   The role must exist before the first deploy of this work: migration `0002` grants it table rights only if it exists. A different
   name works too: after the migrations, run `psql "$MIGRATION_DATABASE_URL" -v app_role=<name> -f scripts/admin/grant_app_role.sql`.
   Check that it is unprivileged: `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'gap_app';` must give `f | f`.
4. **Set the two database URLs on the API service** (`sync: false` secrets), with the same host and pooler setting as before:
   - `MIGRATION_DATABASE_URL`: the owner role's URL. It is used by `alembic upgrade head` and by `scripts/admin/identity.py`.
   - `DATABASE_URL`: the `gap_app` URL. The API refuses to start if it is a superuser or `BYPASSRLS` role.
5. **Deploy the API.** The start command applies the migrations in order:
   - `0001` baseline: on the hosted database it changes no table and only records the version.
   - `0002` identity and tenancy: backfills every existing row to the tenant `default` (with the knowledge bases `legal`, `kyc_aml`, `default`) and enables row-level security. It drops and recreates indexes on live tables and takes a short lock, so deploy at low traffic.
   - `0003` principal lookup, `0004` least privilege for `gap_app`.
   - `0005` gateway: adds `policies` and `gateway_decisions`, with explicit grants to `gap_app` (SELECT on `policies`; SELECT and INSERT on `gateway_decisions`). No new secret is needed.
   - `0007` embedding provenance: adds `embedding_model` and `embedding_dim` to `documents` and sets them NOT NULL. See the rule below.

   **Deploy migration `0007` and the new image together.** Old images do not write `embedding_model` or `embedding_dim`. Once `0007` sets the columns NOT NULL, an old image cannot insert a document. So do not run `0007` while an old image is serving, and do not roll back to an old image after it. The start command runs the migration and starts the new image in one deploy, so use that and do not run `alembic upgrade head` by hand ahead of the deploy.

   **Check `EMBED_MODEL` and `EMBEDDING_DIM` before the deploy.** `0007` labels every existing row with the configured `EMBED_MODEL`. The preview corpus was embedded with the public-preview model, so `EMBED_MODEL` on the API service must name that model. A wrong value labels the rows wrongly and retrieval then skips them as stale. `0007` also stops with a clear message if any stored vector is not `EMBEDDING_DIM` wide. It changes nothing in that case. Fix the setting and deploy again.

   Existing data stays readable by the `default` tenant. Confirm the head with `poetry run alembic current` (owner URL in `MIGRATION_DATABASE_URL`): it must print `0007`.
6. **Create the preview principal and its key** with the admin CLI, from a machine that can reach Neon, using the owner URL. The key is printed once; copy it straight into the Render dashboard:
   ```bash
   export MIGRATION_DATABASE_URL='<owner url>'
   poetry run python scripts/admin/identity.py create-principal default service ui-preview
   poetry run python scripts/admin/identity.py create-key <principal-id> --scopes query kb:read agent
   ```
   To keep the existing hosted data visible, create the principal in the `default` tenant (above). To start clean,
   run `create-tenant preview` and `create-kb preview kyc_aml` first and use `preview` instead.
   The scopes follow Q5: asking and reading only, no `kb:write`. The agent scope is included because the
   UI's Ask page has an agent mode. Uploads need a separate key with `kb:write`.
7. **Set `PREVIEW_PRINCIPAL_ID`** on the API service (`sync: false`) to the id of that principal and redeploy the API.
   Visitors then get a read-only session at `POST /v1/session/preview`. The UI proxy adds no key.
8. **Check after the deploy:**
   - `curl https://<api>/health` gives `db`, `redis` and `embedding` `"ok"` and `"mode":"public-preview"`.
   - `curl https://<api>/v1/documents` gives 401. The same call with the key gives the documents.
   - The UI loads and answers a question.
   - Revoke a leaked key with `scripts/admin/identity.py revoke-key <prefix>` (effective on the next request).

After the deploy, behaviour to know:
- **No policy row means the platform default**, the same access as before (what the key's scopes grant). Restrict a
  tenant with `poetry run python scripts/admin/identity.py set-policy <tenant> policy.json` (owner URL in
  `MIGRATION_DATABASE_URL`); `show-policy <tenant>` prints it. A new version applies from the next request (Q8).
- **Redis is required** for search, ingest and agent runs. If it is unreachable they answer 503 `dependency_unavailable`.
- **Every governed call adds a row to `gateway_decisions`** (no retention yet, Q7). It holds a hash of the input, never the text. If that row cannot be written on an allow, the call answers 503 `decision_unrecorded`.
