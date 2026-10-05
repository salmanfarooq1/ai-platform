# Sprint 008: Build log

## Plan
1. Chain and receipts: `gateway/chain.py` (canonical JSON, hashes, chain check), `gateway/receipts.py` (Ed25519 keyring, sign, verify), migration `0009`, chained decision write, `/v1/receipts/*`, `scripts/verify/receipt.py`.
2. Retention: `purge_decisions` job kind, narrow SECURITY DEFINER purge function, daily scheduler in the worker, `identity.py set-retention`.
3. Eval gate: `scripts/eval/run_gate.py`, `baseline.json`, `run_real.py`, CI step.
4. Cost breaker: `cost` stage, `daily_cost_cap_usd` in the policy, Redis cost counter.
5. Metrics: OpenTelemetry meters with the Prometheus reader, `/metrics`, compose profile `observability`.
6. UI: Trust page, decision drawer action, Playwright and axe.
7. Docs, evidence, report.

## Log
- Built chain, receipts, retention, cost stage, metrics, eval gate, compose profile and Trust UI in that order. Every item has tests.
- Poetry: added `opentelemetry-exporter-prometheus` and moved `deepeval` into the `dev` group (the gate runs in CI).
- Broke and fixed: `$1::text` lock argument needed `str(tenant)`; the owner needs an `owner_access` policy on `chain_heads` for a non-superuser owner; this FastAPI includes routers lazily, so the metrics route label is rebuilt from the path and `path_params`; `set_retention` needed `str(uuid)`; `asyncio.run` inside a test loop (run the gate in a thread).
- Hosted modes now need `RECEIPT_SIGNING_KEY`: four existing tests gained the env var, and `scripts/e2e/serve.py --preview` makes a throwaway key in memory.
- After the usage-limit stop: Docker was down, restarted it. First full run had 4 failures (all expectations that changed on purpose, see report), fixed; second full run green.
- Prometheus and Grafana images pulled here, so `scripts/verify/observability.sh` ran live and passed (`evidence/observability-live.txt`).
