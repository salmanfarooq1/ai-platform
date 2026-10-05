# Sprint 008: Trust baseline. Requirements

A vertical slice: receipts, metrics and retention, plus the Trust pages.

## Contract first
- `GET /v1/receipts/{decision_id}` returns a signed receipt `{decision, signature, key_id, alg}`. The signature is Ed25519 over a canonical JSON form of the decision.
- `GET /v1/receipts/keys` returns the public keys.
- `GET /v1/trust/summary` returns the eval gate status, the retention policy and the metrics links.
- All of these are gated with `audit.read`.

## Scope
1. **Audit receipts.**
   - Each decision row gets a hash chain per tenant: `prev_hash` and `row_hash` (migration 0009).
   - Receipts are signed with a key loaded from settings. In local mode, a dev key is generated at startup and never written to the repo.
   - A verify script checks a chain and a receipt offline.
2. **Retention and purge for `gateway_decisions` (Q7).**
   - A per-tenant `retention_days` with a platform default of 90, a purge job on the 007 queue, and a chain checkpoint row so verification still works after a purge.
   - The default is recorded in DECISIONS and can be changed by setting.
3. **Eval regression gate in CI.** The existing DeepEval harness runs on a small fixed set with the fake LLM in CI. It fails if scores drop below a stored baseline. The real-provider run is a manual script.
4. **Cost circuit breaker.** A per-tenant daily cost cap as a gateway stage. Over the cap gives 429 `cost_cap_exceeded`, fail closed.
5. **Metrics.**
   - OpenTelemetry metrics exported in Prometheus format at `/metrics`, unauthenticated only when `METRICS_PUBLIC=true` (default off; in local it's on).
   - The metrics: request counts and latency per route, decisions per outcome, jobs per status, and outbox lag.
   - An optional compose profile `observability` with Prometheus and Grafana, plus one provisioned dashboard.
6. **UI: Trust pages.**
   - Receipt verification: paste a decision id, see the signature valid or invalid and the chain position.
   - Retention settings (read-only).
   - The eval gate history.
   - Links to Grafana when the profile is on.
