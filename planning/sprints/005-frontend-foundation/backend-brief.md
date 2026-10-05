# Sprint 005: Backend builder brief

You are the backend Builder for Sprint 005 in `/home/user/ai-platform`. You work autonomously and fix your own problems.

## Read first
1. `AGENTS.md`
2. `planning/STATE.md`
3. This folder: `requirements.md`, `blueprint.md` (the contract; don't change it without saying so) and `acceptance.md` (A1-A3, and the backend part of A6)
4. `docs/adr/0006-*` and the gateway code (`gateway/`, `api/auth.py`, `api/middleware/`)

## Build
1. **Scope and action:** `audit:read` and `audit.read`, with the scope map and the CLI (blueprint §1).
2. **Web edge** in `api/web_edge/` (blueprint §2):
   - The session store in Redis.
   - The routes.
   - Cookie auth in the existing auth middleware, after bearer.
   - The CSRF check.
   - The preview session.
   - The `PREVIEW_PRINCIPAL_ID` setting with validation.
   - The per-IP rate limit on sign-in.
3. **Console endpoints and Pydantic models** (blueprint §3). Use `tenant_connection` and `enforce()`. Reuse the existing query helpers where they exist.
4. **`scripts/e2e/serve.py`** (blueprint §5).
5. **ADR:** write `docs/adr/0007-web-edge-session.md` in the style of ADR-0006.
   - **Context:** RFC 10017 recommends keeping tokens server-side. With one web client, a separate BFF service is not worth it.
   - **Decision:** a thin web edge inside the monolith.
   - **Revisit when:** a mobile app, a second client or server rendering arrives.
   - **Consequences.**
6. **OpenAPI:** update the snapshot with `scripts/update_openapi.py`.

## Tests
These are real tests against real Postgres and Redis. Assert decision rows and RLS as `gap_app`. Cover every A2 and A3 bullet. Add a property test for cursor round-trips.

## Run
If Postgres, Redis or dockerd is down, start it:
```
(dockerd > /tmp/dockerd.log 2>&1 &)
docker compose up -d postgres redis
```
Then run:
- `poetry run ruff check api core gateway tests scripts/e2e`
- `poetry run mypy`
- `scripts/check_no_ddl.sh`
- the full pytest suite

The target is 0 failed and 0 skipped. Save the outputs to `evidence/backend-*.txt`, `evidence/web-edge.txt` and `evidence/console-api.txt`.

## Rules
- Never weaken, skip or delete tests.
- No secrets in code or logs.
- No commits or pushes.
- No "demo" wording.
- No dates or durations in plans.
- Simple sentences.
- Don't touch `ui/`, because the frontend builder owns it.

## Return (text)
- The files changed.
- The test numbers.
- Every A1-A3 check, with done, not done or uncertain, and the evidence.
- Any contract deviation.
- Decisions and open questions.
