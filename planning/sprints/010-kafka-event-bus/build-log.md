# Sprint 010: Build log

## Plan
1. Read the pack, the ports and the outbox code. Check what the container can pull (Redpanda, `aiokafka`).
2. Pin `aiokafka` and add the settings (`EVENT_BUS=kafka`, `KAFKA_*`) with validation.
3. `adapters/kafka_event_bus.py`: producer, binary content mode, consumer group, dedupe, dead-letter topic. Wire the relay (`workers/context.py`), the registry and the shutdown.
4. `tests/fake_kafka.py`, then the contract param, unit, integration and e2e tests.
5. Compose profile `kafka`, `scripts/verify/kafka.sh`, the live run.
6. Docs: ADR-0008, runbook, ARCHITECTURE, README, `.env.example`, CHANGELOG, STATE, ROADMAP, QUESTIONS.
7. Full checks, UI checks, `report.md`.

## Log
- **Facts first.** `docker.redpanda.com` is forbidden for the daemon, but `redpandadata/redpanda:v24.2.7` and `apache/kafka:3.8.0` pull from Docker Hub. PyPI has `aiokafka` 0.14.0. So a live run is possible.
- **Design choice.** With `EVENT_BUS=kafka` the registry still returns the outbox bus for the request path (blueprint rule: Kafka only in the relay). `make_relay` builds the Kafka bus as the relay target. `OutboxRelay.aclose` closes the producer on shutdown (worker and embedded).
- **Consumer shape.** `subscribe` keeps the port meaning (in-process, with `tx`), which is how the bus passes the shared contract suite. `consume` is the consumer-group path. The wire client is behind two small protocols so the fake broker exercises the adapter's real logic.
- **Broke and fixed.** `aiokafka` clients need a running loop when built: the wrappers now build them in `start()`. The dead-letter test read the dead-letter topic before the bad record's partition was polled: it now polls a few more times. The first e2e test used `/v1/search`, which needs a knowledge base: it uses `GET /v1/jobs`, which also writes a decision row.
- **One test body, two brokers.** `KAFKA_LIVE_BOOTSTRAP` switches `tests/kafka_helpers.make_bus` from the fake to `aiokafka`. The test id carries `kafka-fake` or `kafka-live`. Nothing is skipped.
- **Live run.** `scripts/verify/kafka.sh` passed 16 tests on Redpanda v24.2.7 (`evidence/kafka-live.txt`).
- **Lock file.** `poetry lock` also added two packages that `pyproject.toml` already listed (B16).
