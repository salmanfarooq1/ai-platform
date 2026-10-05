#!/usr/bin/env bash
# Live check of the `observability` compose profile (Sprint 008, A6): Prometheus scrapes the API and Grafana serves the
# provisioned dashboard. Needs docker, the Prometheus and Grafana images (pulled on first use) and a running Postgres and
# Redis (`docker compose up -d postgres redis`). It starts the end-to-end API (fake providers, throwaway database) on
# :8000, so nothing else may be listening there. Prints each check and exits 1 on the first failure. Writes no secret.
set -u
cd "$(dirname "$0")/../.."
fail() { echo "FAIL $*"; cleanup; exit 1; }
cleanup() {
  [ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null
  docker compose --profile observability stop prometheus grafana >/dev/null 2>&1
}
trap cleanup EXIT

docker compose --profile observability config >/dev/null || fail "compose profile file is not valid"
echo "ok   docker compose --profile observability config"
docker compose --profile observability up -d prometheus grafana >/dev/null 2>&1 || fail "could not start prometheus and grafana (image pull?)"
echo "ok   prometheus and grafana started"

STATE_DIR=$(mktemp -d)
poetry run python scripts/e2e/serve.py --port 8000 --host 0.0.0.0 --state-dir "$STATE_DIR" >/tmp/observability-api.log 2>&1 &
API_PID=$!
for _ in $(seq 1 90); do curl -fs http://127.0.0.1:8000/v1/health >/dev/null 2>&1 && break; sleep 2; done
curl -fs http://127.0.0.1:8000/v1/health >/dev/null || fail "the API did not start (see /tmp/observability-api.log)"
curl -fs http://127.0.0.1:8000/metrics | grep -q "^# TYPE http_requests_total counter" || fail "/metrics has no http_requests_total"
echo "ok   API serves /metrics"

for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:9090/api/v1/targets" | python3 -c "import json,sys; t=json.load(sys.stdin)['data']['activeTargets']; sys.exit(0 if any(x['labels']['job']=='api' and x['health']=='up' for x in t) else 1)" && break
  sleep 3
done
curl -fs "http://127.0.0.1:9090/api/v1/targets" | python3 -c "import json,sys; t=json.load(sys.stdin)['data']['activeTargets']; sys.exit(0 if any(x['labels']['job']=='api' and x['health']=='up' for x in t) else 1)" || fail "Prometheus does not see the api target as up"
echo "ok   Prometheus scrapes the api target (up)"
for _ in $(seq 1 20); do
  N=$(curl -fs "http://127.0.0.1:9090/api/v1/query?query=http_requests_total" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['data']['result']))")
  [ "${N:-0}" -gt 0 ] && break; sleep 3
done
[ "${N:-0}" -gt 0 ] || fail "Prometheus has no http_requests_total series"
echo "ok   Prometheus holds http_requests_total ($N series)"

for _ in $(seq 1 30); do curl -fs http://127.0.0.1:3000/api/health >/dev/null 2>&1 && break; sleep 2; done
curl -fs http://127.0.0.1:3000/api/health >/dev/null || fail "Grafana is not up"
curl -fs "http://127.0.0.1:3000/api/search?query=Platform%20trust" | grep -q "platform-trust" || fail "the dashboard is not provisioned"
echo "ok   Grafana serves the provisioned dashboard 'Platform trust'"
curl -fs http://127.0.0.1:3000/api/datasources | grep -q '"uid":"prometheus"' || fail "the Prometheus data source is not provisioned"
echo "ok   Grafana has the Prometheus data source"
echo "PASS"
