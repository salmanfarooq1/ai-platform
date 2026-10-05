# Sprint 008: Blueprint (contract first)

## 1. API contract (typed, `/v1`, OpenAPI, all `audit:read` unless noted)
| Method | Path | Response |
|---|---|---|
| GET | `/v1/receipts/{decision_id}` | `Receipt {decision: DecisionDetail, chain: {prev_hash, row_hash, position}, signature: base64, key_id, alg: "Ed25519", canonical: str}`. Foreign or missing gives an identical 404 |
| GET | `/v1/receipts/keys` | `[{key_id, alg, public_key: base64, active: bool}]`. No secret |
| POST | `/v1/receipts/verify` | Body: a `Receipt`. Returns `{valid: bool, checks: [{name, ok, detail}]}`. The server-side helper does the same checks as the offline script |
| GET | `/v1/trust/summary` | `{retention_days, oldest_decision_at, last_purge_at, eval_gate: {status, baseline, latest, run_at}\|null, metrics_public: bool}` |
| GET | `/metrics` | Prometheus text format. Public only when `METRICS_PUBLIC=true` (the default is true in local and false elsewhere). Otherwise it needs `admin` |

## 2. Data (migration 0009)
- **Hash chain:** `gateway_decisions` gets `prev_hash` and `row_hash` (both nullable for old rows), plus a per-tenant chain head.
  - `row_hash = sha256(canonical_json(decision fields) || prev_hash)`.
  - Rows are chained in insert order per tenant, under an advisory lock per tenant.
  - Old rows get a genesis checkpoint.
- **`chain_checkpoints`:** `tenant_id`, `position`, `row_hash`, `created_at`, `reason` (genesis or purge).
- **`tenants`:** gets `retention_days int null`. The platform default is set by `DECISION_RETENTION_DAYS`, default 90.
- **`eval_runs`:** `id`, `suite`, `scores jsonb`, `baseline jsonb`, `passed`, `run_at`.

## 3. Components
- **Signing key:** `RECEIPT_SIGNING_KEY` (Ed25519 private key, base64) is required in `public-preview` and `prod`. In `local`, an ephemeral key is generated at startup and logged by `key_id` only. The key is never written to disk or to the repo. Key rotation keeps the old public keys listed.
- **`scripts/verify/receipt.py`:** checks a receipt offline, given the public key.
- **Purge job:** a Sprint 007 job kind `purge_decisions`, scheduled daily by the worker. It writes a checkpoint first, then deletes the expired rows of one tenant in batches.
- **Eval gate:**
  - `scripts/eval/run_gate.py` runs a fixed small suite with the fake LLM and compares it to `scripts/eval/baseline.json`.
  - CI fails on a regression larger than a tolerance.
  - `scripts/eval/run_real.py` is the manual run with real providers. It needs keys and is never run in CI.
- **Cost breaker:** a gateway stage `cost` after `budget`, with a per-tenant daily cost cap (`daily_cost_cap_usd` in the policy, plus a platform default).
  - Over the cap, the call gets 429 `cost_cap_exceeded`.
  - If Redis is down, the call is denied (fail closed).
  - Add `cost_cap_exceeded` to `gateway/reasons.py`.
- **Metrics:** OpenTelemetry metrics with the Prometheus exporter.
  - `http_requests_total` and `http_request_duration_seconds` (route, method, status).
  - `gateway_decisions_total` (action, outcome, stage).
  - `jobs_total` (kind, status) and `outbox_lag_seconds`.
- **Compose profile `observability`:** Prometheus (scrapes the API) and Grafana with one provisioned dashboard JSON. Both are pinned images.

## 4. UI (follows `docs/design/`)
- **Trust page** (replaces the placeholder):
  - Receipt verification: paste a decision id, then fetch, verify, and show valid or invalid, with each check, the chain position and the `key_id`.
  - Retention: days, oldest record, last purge.
  - Eval gate: the latest status and the history.
  - A Grafana link when configured.
- **Decision drawer:** a "Verify receipt" action.
- **Content:** signed receipts may now be claimed. Update `docs/design/CONTENT_STYLE.md` (move them from must-not to may-claim) and the landing copy only where it's accurate.
