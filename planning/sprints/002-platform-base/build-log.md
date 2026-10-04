# Sprint 002: Build log

## Plan
1 baseline; 2 ruff + B1/B2; 3 Settings; 4 Alembic; 5 /v1 + errors; 6 logging/OTel; 7 mypy; 8 test harness; 9 CI; 10 UI; 11 docs; then evidence + report.

## Log
- Baseline saved (evidence/baseline-*.txt). Unit collection fails on tests/unit/test_llm.py (B1). Ruff: 33 errors.
- B1/B2 fixed, ruff clean (ruff --fix incl. unsafe whitespace-in-docstring fixes), 82 unit pass.
- Settings, Alembic 0001 (fresh+existing evidence saved), /v1, errors.py, observability.py, middleware reordered (RequestID outermost after CORS so 429 bodies carry request_id), schema.sql deleted.
- mypy passes with no ignore_errors (found real bug: transport used mcp._mcp_server, SDK 2 has _lowlevel_server; fixed).
- tests/fakes.py, network guard (tests/conftest.py autouse) done; 106 unit pass. Next: harness + integration/e2e.
- integration tier: 19 tests pass (migrations, lifecycle, retrieval, usage/feedback).
- e2e tier done (SSE endpoint converted to raw ASGI route; real MCP initialize round-trip tested). 60 int+e2e pass.
- docker build blocked by Docker Hub 429 (anonymous pull limit); ECR mirror blobs 403 (egress policy, not bypassed). Retrying with backoff.
- Found and fixed: MCP SSE route used `mcp._mcp_server` (absent in MCP SDK 2.x). Route is now a raw ASGI route (`api/mcp/transport.py` `SseApp`), because a FastAPI endpoint function sends a second response when the session ends. Real MCP `initialize` round trip is tested.
- Redis: RediSearch cannot create an index outside db 0, so tests use db 0 and delete only platform-owned keys (QUESTIONS B7).
- The deepeval pytest plugin crashed the skip summary (rich markup). Disabled with `-p no:deepeval` in `pyproject.toml`.
- Docker build (A9): Docker Hub `429` first. Then the base image pulled, but pip inside the build container failed TLS verification behind the sandbox egress proxy. Adding the proxy CA to a base image and a lint-only build were both denied by the sandbox policy, so I stopped and did not work around it. Closest check: the Dockerfile CMD run directly on a fresh DB (`evidence/docker-run.txt`).
- Final evidence captured. All checks done except A9.
