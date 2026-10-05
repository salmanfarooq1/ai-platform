# Risks

| # | Risk | Effect | Mitigation |
|---|---|---|---|
| R1 | The hosted service still has `MODE=demo` after the rename | The service fails at startup (by design) | Set `MODE=public-preview` before or with the deploy (runbook, Q2) |
| R2 | The first Alembic migration runs against the live Neon database | Data loss or downtime | A baseline migration that matches the current schema exactly, a backup or Neon branch first, and an additive-only first step (Q4) |
| R3 | Adding row-level security and `tenant_id` breaks existing queries | Empty results or errors on the live preview | Backfill with a default tenant, keep the policies permissive until the app sets the tenant, and run integration tests before enabling |
| R4 | The scope of the vision is too wide | Every layer ends up half-built | Thin walking skeletons, one sprint per layer, with acceptance checks as the gate |
| R5 | Free-tier limits (512MB RAM, cold starts, Neon compute hours) | Slow or failing preview | Keep the reranker off in `public-preview`, keep-awake is a Phase 1 item, measure memory each sprint |
| R6 | CI is red on `main` because of the 33 existing lint errors | New lint failures get hidden | Closed in Sprint 002: `ruff check` is clean (`DECISIONS.md`) |
| R7 | Cheaper Builder models drift from the brief | Scope creep, weakened tests | Precise briefs, a QA review, and the Architect re-runs the checks |
| R8 | Docker is unavailable in some environments | Integration tests never run | Integration tests skip cleanly, and CI runs them with service containers |

## From Sprint 003 QA
- **The preview key is shared.** Every public visitor uses one principal, so one visitor can use up the rate limit and the tenant's token budget for everyone. This is accepted for the preview. The fix is per-visitor keys or an IP limit at the proxy.
- **JWT scopes are trusted from the issuer.** A compromised signing key amounts to full tenant access. Later: intersect the token's scopes with a per-principal maximum.
- **Migration 0002 drops and recreates indexes** on live tables, which takes a short lock on the hosted DB. Deploy it at low traffic.
- **Redis errors failed open** for the rate limit and budget. Closed in Sprint 004: both are gateway stages and fail closed with a 503.

## From Sprint 004 QA
- **N2:** the gate-call lint checks that a gate call exists, not which actions it passes. A tool could call the gate with the wrong action. Review new tools by hand.
- **N3:** MCP scope denials leave no decision row. REST scope denials do.
- **N5:** parallel tool calls can overshoot `max_tool_calls` by the number of calls in flight.
- **N6:** a call denied with `decision_unrecorded` has already used up its rate and budget counters.
- **N7:** ingest embedding is not bounded by `max_tokens_per_request`.
- **N8:** some error bodies include exception text. Most of this predates Sprint 004.
- **N9:** the public health probe calls the embedding provider, so anyone can trigger an embedding call.
- **S5-1:** `auth_lookup_preview` (migration 0006) lets the app role read any principal's tenant and key scopes, given its UUID. UUIDs can't be guessed, and no secret is returned. Accepted.
- **S5-2:** a live cookie session keeps the scopes from sign-in until it expires (8 h sliding, 24 h cap). A revoked key or a disabled principal ends it at once; a scope change needs a new sign-in.

## From Sprint 005b QA
- **S5b-1:** the overview and requests queries group the tenant's whole decision history on each call. This is fine at current volume. Retention (Sprint 008) and a `created_at` pre-filter bound it.

## From Sprint 009 (builder, not yet reviewed by QA)
- **S9-1:** the agent in the sandbox holds a live run token for the run's wall limit plus a minute. Anything that runs in the sandbox can use it, but only on that run's two routes, under the run's fixed boundary, and it is revoked when the run ends. A compromised agent can still spend that run's model budget and tool calls up to the boundary.
- **S9-2:** sandbox events are an observation, not a record the platform can vouch for. They are not on the hash chain, a failed write is logged and the run continues, and the `file_denied` and `limit_hit` rows can come from the agent's own report or an exit code (`source` says which). Use the gateway decisions as the control record.
- **S9-3:** OpenShell logs nothing when Landlock refuses a file read, so an agent that tries a forbidden read leaves no event (Q37). The read is still refused.
- **S9-4:** the pin is a version and checksums, not a signature. The checksum file sits next to the files on the same host. Q33 asks who bumps the pin.
- **S9-5:** the live result is for one setup: OpenShell 0.1.2, Docker driver, a gateway from the Debian package, runtime images rebuilt locally from checksum-checked archives, a local workload image. The standard images, other drivers and other hosts are untested.
- **S9-6:** the event rules in `adapters/openshell_events.py` read OpenShell's log text. A release that changes the wording turns a denial into a plain `log` row (never into a false denial). Re-run `scripts/verify/openshell.sh` when the pin moves.
- **S9-7:** the cost in a sandboxed answer is the figure the agent reported (Q40). The booked usage is measured at the gateway.
- **S9-8:** each sandbox call is an HTTP request and writes decision rows (and outbox rows). A run with many tool calls writes many rows, the same family as Q24.
- **S9-9 (accepted, QA L4):** the run token crosses the Docker bridge over plain HTTP. The bridge is host-local and the token is short-lived. TLS to the gateway is a hosting item (Q38).
- **S9-10 (accepted, QA L5):** the base images in the runbook are not pinned by digest, because digests could not be fetched here. The runbook tells the operator to pin by digest on first pull.

