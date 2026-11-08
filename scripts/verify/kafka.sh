#!/usr/bin/env bash
# Live Apache Kafka contracts. Existing stores are never removed by this script.
# Set KAFKA_BOOTSTRAP to use an existing broker; otherwise start the optional streams services.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ -z "${KAFKA_BOOTSTRAP:-}" ]; then
    command -v docker >/dev/null || { echo "docker is needed (or set KAFKA_BOOTSTRAP)"; exit 2; }
    docker compose --profile streams up -d --wait kafka
    docker compose --profile streams run --rm kafka-topics
    export KAFKA_BOOTSTRAP="localhost:19092"
fi

echo "Live Kafka contracts; client aiokafka $(poetry run python -c 'import aiokafka; print(aiokafka.__version__)')"
export KAFKA_LIVE_BOOTSTRAP="$KAFKA_BOOTSTRAP"
poetry run pytest -p no:cacheprovider -v -rs \
    tests/contracts/test_event_bus_contract.py -k "kafka-live" \
    tests/integration/test_kafka_bus.py tests/e2e/test_kafka_flow.py
