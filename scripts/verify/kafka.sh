#!/usr/bin/env bash
# Run the Kafka adapter against a live Redpanda (Sprint 010, acceptance A1 to A4 "live run").
#
#     scripts/verify/kafka.sh                         # starts the `kafka` compose profile, runs the tests, stops it
#     KAFKA_BOOTSTRAP=host:9092 scripts/verify/kafka.sh   # uses a broker you already run; nothing is started
#
# It runs the shared EventBus contract suite (`kafka-live` ids), the consumer, dead-letter, restart and ordering tests
# (1,000 events over 3 tenants), and the end-to-end decision-to-consumer test. They are the same tests that run on the
# in-memory broker in the normal suite. KAFKA_LIVE_BOOTSTRAP makes them use aiokafka and a real broker instead.
# Needs Postgres and Redis (`docker compose up -d postgres redis`) and Docker for the broker. Linux or WSL.
set -euo pipefail
cd "$(dirname "$0")/../.."

started=""
cleanup() {
    if [ -n "$started" ]; then
        docker compose --profile kafka rm -sf kafka-topics redpanda >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [ -z "${KAFKA_BOOTSTRAP:-}" ]; then
    command -v docker >/dev/null || { echo "docker is needed to start Redpanda (or set KAFKA_BOOTSTRAP)"; exit 2; }
    started=1
    docker compose --profile kafka up -d redpanda
    for _ in $(seq 1 60); do
        [ "$(docker inspect -f '{{.State.Health.Status}}' redpanda 2>/dev/null)" = "healthy" ] && break
        sleep 2
    done
    [ "$(docker inspect -f '{{.State.Health.Status}}' redpanda)" = "healthy" ] || { docker logs --tail 30 redpanda; echo "redpanda did not become healthy"; exit 1; }
    docker compose --profile kafka up kafka-topics
    export KAFKA_BOOTSTRAP="localhost:19092"
fi

echo "== broker: ${KAFKA_BOOTSTRAP}"
echo "== client library: aiokafka $(poetry run python -c 'import aiokafka; print(aiokafka.__version__)')"
export KAFKA_LIVE_BOOTSTRAP="$KAFKA_BOOTSTRAP"
poetry run pytest -p no:cacheprovider -v -rs \
    tests/contracts/test_event_bus_contract.py -k "kafka-live" \
    tests/integration/test_kafka_bus.py tests/e2e/test_kafka_flow.py
