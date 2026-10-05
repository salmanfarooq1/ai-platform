# Questions

Open items that need a human answer. Work continues around them. When one is answered, delete it and record the answer in `DECISIONS.md`.

- **Q1.** The local dev machine is WSL Ubuntu 22.04. The commands in `AGENTS.md` were verified in a Linux cloud container (Python 3.11, Poetry 2.3, Node 22, Docker CLI present but no daemon). Confirm they work the same in WSL, especially Docker Desktop and Ollama.

## Sprint 003
- **Q5.** Public visitors of the hosted UI: should the preview key allow uploads (`kb:write`), or only asking questions? Default taken: query + read only; uploads need a separate key. Built that way, with one addition: the documented preview key also has the `agent` scope, because the UI's Ask page has an agent mode and would 403 without it. Say if the preview should be search-only.

## Sprint 004
- **Q7.** Retention of `gateway_decisions`: one row per governed call grows without bound (a search writes two or more, an agent run one per model and tool call). How long are decision records kept, and is there a purge or archive job? Left open; Sprint 007 extends the table and is the place to decide. No purge exists.
- **Q8.** Hosted rollout of migration `0005`: it grants `gap_app` SELECT on `policies` and SELECT, INSERT on `gateway_decisions` only when the role exists (it does on Neon once B9 is done). Until a tenant is given a policy with `set-policy`, the platform default (what scopes grant) applies. Who writes the first real tenant policies?
- **Builder, Sprint 004, B10.** Redis-down behaviour changed deliberately. Before: the rate limiter and the budget check logged a warning and let the request through. Now: search, ingest and agent runs answer 503 `dependency_unavailable` (Sprint 003 QA finding M2, closed in Sprint 004). Opening an MCP session needs Redis too. Confirm this is wanted on the free tier, where Redis may be flaky.
- **Builder, Sprint 004, B11.** Docker image builds are still blocked in this sandbox, so the image was not rebuilt. The runtime stage of `Dockerfile` copies packages one by one, so a `COPY --from=builder /app/gateway gateway/` line was added (without it the image would fail to import `gateway`). Run `docker build .` where Docker Hub is reachable to confirm.

## Builder, Sprint 003
- **B8.** Docker image builds do not work in this sandbox (proxy TLS), so `ui/Dockerfile.ui` (nginx template, key guard script) and the API image start command were checked by unit tests and by reading, not by a real build and run. Run `docker build -f ui/Dockerfile.ui ui` and start it with and without `PREVIEW_API_KEY` where Docker Hub is reachable.

## Builder, Sprint 002
- **B5.** `MODEL_PRICING` has `gemini/gemini-3.5-flash-lite` at `$0 / $0` (free tier) so the config's own model has an entry. What rates apply once the key is on a paid plan?
- **B6.** Docker Hub returned `429 Too Many Requests` for the `python:3.11-slim-bookworm` base image, so `docker build` (A9) could not be completed in the Builder container. See `report.md`. Re-run `docker build -t gap-api .` where Docker Hub is reachable.
- **B7.** The integration and e2e tests use Redis database 0, not 15, because RediSearch can only create the semantic-cache index in database 0. They delete only platform-owned keys (`rl:`, `budget:`, `cache:`, `semcache:`) and refuse to run if database 0 holds any other key.

## Found in the docs pass
- **Q9.** `scripts/labs/lab_6.3_model_routing.py` imports `classify_query_complexity`, which commit `efde99f` removed from `api/services/llm.py` (Decision 7). The lab no longer runs. Keep it as a historical record, or restore a copy of the classifier inside the lab?

## Sprint 005 setup
- **Q11.** This container's network policy blocks `21st.dev` and `threeui.com` (proxy 403). GitHub and npm work. So in this container no component is copied from those sites. The equivalents are built from shadcn/ui (npm) and from three.js, `@react-three/fiber` and `@react-three/drei` (MIT, npm), with sources noted in comments. To use a specific 21st.dev or ThreeUI item, allow those hosts in the environment's network settings, or install the item on your machine with the shadcn CLI and its URL.
- **Q12.** The web edge sign-in limit (10 a minute per client IP) uses the socket address. Behind a hosting proxy that is the proxy's address, so all visitors would share one budget. Which proxy hops can be trusted to set a forwarded address, so a trusted-proxy setting can read it? Until answered, the limit is correct locally and may be too strict when hosted.
- **Q13.** `usage_log` has no principal column, so the console usage summary attributes rows to a principal through the `gateway_decisions` rows with the same request id. Should Sprint 007 add a `principal_id` column to `usage_log`?

- **Q14.** Should the UI get a Storybook component catalogue in a later sprint? It's the common standard for visual review and component docs. It isn't added now, because it brings a large toolchain and `docs/design/COMPONENTS.md` with the Vitest tests covers the need. Sprint 005b.

- **Q15.** `GET /v1/policies` doesn't return the tenant's `blocked_terms`. So when the guardrails block a query, the UI can't show which policy field is behind it. Should the console policy view expose `blocked_terms` (read-only, `audit:read`)? The terms may themselves be sensitive. Sprint 005b.

## Parked: hosting
Deployment is not a concern for now. These wait until it is.
- **Q2.** The hosted service on Render reads `MODE` from `render.yaml` when the Blueprint syncs. After this sprint, does the service get `MODE=public-preview` automatically, or must it be set by hand in the dashboard? Either way, it must be set before or with the next deploy.
- **Q4.** For the hosted Neon database: is there a backup or branch to restore from before the first migration (Sprint 002)?
- **Q6.** The hosted Neon database user: is it the owner role (`neondb_owner`)? Sprint 003 needs a second, non-owner login role for the app so row-level security applies. Creating it on Neon is free; it needs a password set as a Render secret.
- **B9.** Hosted rollout needs a human: create the `gap_app` role on Neon, set `MIGRATION_DATABASE_URL`, `DATABASE_URL` and `PREVIEW_API_KEY` on Render, create the preview key (steps in `docs/render-deployment.md`). Nothing was run against Neon.
- **Q10.** The top of `docs/render-deployment.md` says the first deploy was prepared and not yet done, while `README.md` lists live preview URLs. Which is current? Confirm that the hosted services are live and which migration the hosted database is at.
