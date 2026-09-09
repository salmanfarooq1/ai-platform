# Render Deployment Runbook (MODE=demo)

Status: **prepared and locally verified, not yet deployed.** Everything below
up to "Remaining steps" has been done and tested. The remaining step needs
a dashboard action only you can take (connecting the repo).

---

## What MODE=demo actually requires

`config.py` selects services by `MODE`. In `demo` the platform needs four
things from the environment:

| Variable | Used by | Notes |
|---|---|---|
| `GROQ_API_KEY` | LLM completion (`groq/llama-3.3-70b-versatile`) | Verified working. |
| `GEMINI_API_KEY` | Embeddings (`gemini/gemini-embedding-001`) | Verified working. |
| `DATABASE_URL` | asyncpg pool, pgvector retrieval | Neon Postgres 16 + `vector` extension. |
| `REDIS_URL` | Cache, rate limit, token budget | **Must have the RediSearch module.** |

Plus `MODE=demo` itself, and `WEB_CONCURRENCY=1` to stay inside 512MB.

### Why Redis needs RediSearch

`api/main.py`'s lifespan calls `create_semantic_cache_index()`, which issues
`FT.CREATE` and re-raises anything that is not "Index already exists". On a
Redis without the RediSearch module the command is unknown, the exception
propagates out of startup, and **the app never boots**.

This rules out Upstash. Use Redis Cloud's free Essentials tier (30MB), which
ships RediSearch and JSON. `redis.from_url` accepts its `rediss://` URL as-is.

### Why the embedding model changed

Demo mode used to default to `ollama/nomic-embed-text`, which resolves to
`localhost:11434`. There is no Ollama sidecar on a 512MB Render instance, so
that default could never have worked in the cloud. `/health` would have
reported the embedding probe down and every search would have failed.

It now defaults to `gemini/gemini-embedding-001`. That model emits 3072 floats
natively, so `core/clients/embeddings.py` requests 768 and renormalizes the
truncated vector, keeping the `VECTOR(768)` column in `schema.sql` unchanged.

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

The existing `FEATURES["reranker_enabled"] = MODE != "demo"` flag stopped the
cross-encoder from *loading*, but `api/services/retriever.py` imported
`sentence_transformers` at module scope, so **torch was imported on every
boot regardless of the flag**: roughly 300MB resident and a multi-GB image.

1. `api/services/retriever.py`: `CrossEncoder` is now imported inside
   `get_cross_encoder()`, so the flag genuinely avoids the cost.
2. `pyproject.toml`: `sentence-transformers` moved to a `rerank` dependency
   group, `matplotlib`/`deepeval` to a `labs` group.
3. `Dockerfile`: takes an `INCLUDE_RERANK` build arg, default `false`. Render
   uses the default, so the demo image never installs torch. A prod build
   would set `INCLUDE_RERANK=true` to get the reranker back. See Decision 20
   in `ARCHITECTURE.md`.
4. `core/clients/embeddings.py`: new. Single entry point for all three
   embedding call sites (ingestion, semantic cache, `/health` probe).
5. `/health` now reports the embedding probe as its own field instead of
   folding it silently into `status`.

### Measured result

| | Before | After (demo, `INCLUDE_RERANK=false`) |
|---|---|---|
| Image size | ~3GB (torch) | **119 MiB** |
| RSS after import | not measured | 268 MB |
| Steady-state container RSS | not measured | **240 MiB** / 512MB budget |

---

## Infrastructure already provisioned

### Postgres, Neon: done

Free project created at <https://neon.tech>, pgvector enabled, schema
applied (`core/database/schema.sql`, which starts with `CREATE EXTENSION IF
NOT EXISTS vector` and is self-contained). Corpus ingested: **452 chunks**
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

`render.yaml` at the repo root defines the service (Docker runtime, free
plan, `/health` health check, `MODE=demo`, `WEB_CONCURRENCY=1`) and marks
`GROQ_API_KEY` / `GEMINI_API_KEY` / `DATABASE_URL` / `REDIS_URL` as
`sync: false` so Render prompts for them as masked secrets instead of
reading them from the file.

---

## Remaining steps

### 1. Connect the repo (dashboard action, only you can do this)

1. Push this branch (or merge to `main`) to GitHub.
2. Render dashboard → **New** → **Blueprint** → select this repo.
3. Render reads `render.yaml` and prompts for the four secret env vars.
   Paste in the Groq key, Gemini key, Neon `DATABASE_URL`, and Redis Cloud
   `REDIS_URL`.
4. Deploy. First build installs `poetry install --only main` inside Docker
   and should take a few minutes.

### 2. Verify

```bash
curl https://<service>.onrender.com/health
```

Expect `db`, `redis`, and `embedding` all `"ok"` and `"mode":"demo"`. Then
exercise the deployed corpus:

```bash
curl -X POST https://<service>.onrender.com/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "customer due diligence requirements", "namespace": "kyc_aml"}'
```

Note free-tier Render instances spin down after 15 minutes idle and
cold-start on the next request. Expected on this plan, not a bug.

### 3. README

Add a "Live Demo" section above "Getting Started" with the URL, noting that
the deployment runs `MODE=demo`: reranker disabled, so search is hybrid RRF
(BM25 + vector) without the cross-encoder rerank stage, and only the
`kyc_aml` namespace has data.
