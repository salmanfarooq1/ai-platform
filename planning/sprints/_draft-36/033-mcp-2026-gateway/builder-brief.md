# Sprint 033: Builder brief
You are the Builder for Sprint 033 in `/home/ubuntu/ai-platform`, on branch `sprint/033-mcp-2026-gateway`. This is a vertical slice: contract, transport, registry, UI and e2e tests. Work autonomously and fix your own problems. The stop conditions are in AGENTS.md: a strict-rule or blueprint conflict, a destructive action, a missing secret, or paid spend. On a stop condition, log it in `planning/QUESTIONS.md` and `build-log.md`, skip only that item, and finish the rest.

## Read first
- `AGENTS.md`, `planning/STATE.md`, `planning/DECISIONS.md`, and this folder (all five files).
- `api/mcp/transport.py`, `api/mcp/server.py`, `api/mcp/tools.py`, and the MCP routes in `api/main.py`.
- `core/identity/jwt.py` (`aud` is already required) and the egress allowlist from 018.
- The MCP 2026-07-28 specification (transport, authorization, `_meta`), RFC 9728 and RFC 8707.
- `.claude/skills/governed-design/SKILL.md` for the UI.

## Build
Everything in the blueprint, in this order: contract and settings, migration, the stateless transport and legacy flag, header policy, the audience check and resource metadata, tool pins, `adapters/mcp_client.py` and the registry, the trace extension, UI.

## Tests
- **Baseline:** the numbers in Sprint 032's report. State the delta.
- Write one test per acceptance item and per threat-model row, using the names given there.
- The downstream peer is an in-process MCP server built with the same SDK. It records every header it receives.
- Existing MCP tests that use the SSE transport run with `MCP_LEGACY_SSE=true`, and gain a twin on the new endpoint. Do not delete them.
- No live verify script. Add no new skips.

## Notes from the Architect
- **Pins:**
  - `mcp==2.2.0`, which 011 already pinned.
  - Confirm that it supports protocol 2026-07-28 and stateless streamable HTTP, and record the result in `evidence/pins.txt`.
  - If it does not, stop on item 1 only.
- **Code facts:**
  - `SseApp` opens a session with `enforce(KB_READ, rate=...)`.
  - `MessagesApp` binds `current_principal` per POST. Keep that per-request binding in the stateless handler.
  - `PlatformMCPServer` keeps `_dependency_overrides`. Reuse it.
- **Header names and the `-32020` code:** take both from the 2026-07-28 spec text. If the spec differs from this pack, follow the spec and say so in the report.
- **Root paths (rule 9):**
  - Product routes stay under `/v1`.
  - RFC 9728 metadata lives under `/.well-known/oauth-protected-resource...`. Rule 9 in `planning/program/vision-and-architecture.md` allows it, and Sprint 032 recorded the decision in `planning/DECISIONS.md` and `docs/architecture.md`. Add this path to the list there.
  - Name the metadata URL in `WWW-Authenticate`.
- **No passthrough:** add an import-lint rule so only `adapters/mcp_client.py` opens downstream MCP connections. Also add a unit test that the client's header builder never reads the inbound request.
- **Migration:** use the next free number after Sprint 032's head.
- **Docs:** ADR-0023, `docs/api/mcp.md`, `docs/configuration.md`, `docs/architecture.md` (the rule 9 path list), OpenAPI snapshot, `.env.example`, CHANGELOG (with the test delta and the legacy deprecation), STATE.

## Run
If Postgres, Valkey or dockerd is down, run `(dockerd > /tmp/dockerd.log 2>&1 &)`, then `docker compose up -d --wait`.
```bash
poetry run ruff check api core gateway evidence dataplane lineage insights ports adapters workers sandbox_agent tests scripts/e2e
poetry run mypy
scripts/check_no_ddl.sh
poetry run lint-imports
opa test policy/ -v
poetry run pytest -q -rs --junitxml=planning/sprints/033-mcp-2026-gateway/evidence/pytest.xml
poetry run python scripts/check_skips.py planning/sprints/033-mcp-2026-gateway/evidence/pytest.xml
poetry run python scripts/update_openapi.py
scripts/supply_chain/licence_gate.sh
scripts/ci/edition_smoke.sh
cd ui && npm run gen:api && npm run tokens:check && npm run lint && npm run typecheck && npm test -- --run && npm run build && npm run chunk-report && npm run copy-check && npm run e2e
```
`scripts/ci/edition_smoke.sh` runs all five editions (Sprint 013); CI runs it from `.github/workflows/editions.yml`. `check_skips.py` takes the expected count from `tests/skip_allowlist.json`.

Never run `playwright install`.

## Rules
- Never weaken, skip or delete tests. No secrets in files or logs. No commits or pushes.
- No "demo" wording, no brand names, no model or tool attribution. Use simple sentences in docs.

## Finish
Write `report.md` with:
- the acceptance table with evidence links
- the test numbers and the delta against Sprint 032
- the migration number
- the metadata path served
- deviations and open questions

Add proposed commit blocks per `planning/program/branching-and-commits.md`:
- `feat(protocols): add stateless mcp endpoint and registry contract`
- `feat(db): add mcp registry entries and tool pins`
- `feat(protocols): check mcp headers, audience and pinned tool definitions`
- `test(protocols): cover header mismatch, passthrough and rug pull`
- `feat(ui): add mcp registry page`
- `docs(adr): record mcp 2026-07-28 at the gateway and the private registry`
- `docs(planning): update state and changelog for the mcp gateway`

The Builder does not commit. A human runs the commands.
