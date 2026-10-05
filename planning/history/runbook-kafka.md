# Runbook: Kafka event bus

This is for `EVENT_BUS=kafka` (Sprint 010, ADR-0008). The outbox relay publishes the platform's events to Kafka. The default is unchanged: with `EVENT_BUS` unset, the relay hands events to the in-process bus and nothing here is needed.

## Status
- **Verified in the Sprint 010 build container** on one Redpanda node (`redpandadata/redpanda:v24.2.7`, from Docker Hub) with `aiokafka` 0.14.0, by `scripts/verify/kafka.sh`. Output: `planning/sprints/010-kafka-event-bus/evidence/kafka-live.txt`. The contract suite, the consumer tests, the dead-letter test, the relay-restart test, the 1,000-event ordering test and the end-to-end test all passed on it.
- **Not verified:** more than one broker, replication, a Kafka cluster that is not Redpanda, SASL or TLS against a real broker (the settings are checked and the options are built, but no secured broker was used), several consumers in one group (partition sharing and rebalances), broker restarts during a run, and the Docker image pull from `docker.redpanda.com` (it was refused here; Docker Hub worked).
- The live run checks redelivery more weakly than the fake does: it replays through a new group that reads from the start, since a real group's offset cannot be reset by the test. The fake checks the exact committed-offset case.
- The pytest suite does not need a broker. It runs the same tests on the in-memory broker (`tests/fake_kafka.py`).

## What flows where
```
request -> gateway decision + outbox row (one Postgres transaction)
                                |
                  relay (python -m workers, or EMBEDDED_RELAY)
                                |  publish, wait for the acknowledgement, mark sent
                                v
                  Kafka topic platform.<type>      key = tenant id
                                |
                  consumer group KAFKA_GROUP_ID  -> handler (deduped by CloudEvent id)
                                |  after KAFKA_MAX_ATTEMPTS failures
                                v
                  platform.<type>.dlq
```
- Kafka is never reached inside a request. A Kafka outage leaves events in the outbox. The relay logs the error, counts the attempt and tries again on the next pass. After `OUTBOX_MAX_ATTEMPTS` a row is left for an operator.
- Topics: `platform.gateway.decision`, `platform.ingest.completed`, `platform.gateway.purge`, and each with `.dlq`.
- A record is a CloudEvent in binary mode: `ce_*` headers and the JSON data as the value.

## Run it locally
```bash
docker compose up -d postgres redis
docker compose --profile kafka up -d redpanda        # one node, localhost:19092 for the host
docker compose --profile kafka up kafka-topics       # creates the topics (3 partitions each), then exits
export EVENT_BUS=kafka KAFKA_BOOTSTRAP=localhost:19092
poetry run python -m workers                         # the relay publishes to Kafka
```
Look at a topic:
```bash
docker exec redpanda rpk topic consume platform.gateway.decision -n 3 -f 'key=%k headers=%h{%k:%v,} value=%v\n'
docker exec redpanda rpk topic consume platform.gateway.decision.dlq -n 3
```
Stop it with `docker compose --profile kafka rm -sf kafka-topics redpanda`. Do not use `down -v` for this: it removes the Postgres volume too.

## Check it live
`scripts/verify/kafka.sh` starts the profile, runs the tests against it and stops it again. With a broker you already run: `KAFKA_BOOTSTRAP=host:9092 scripts/verify/kafka.sh` (nothing is started or stopped). It needs Postgres and Redis and, for the broker, Docker on Linux or WSL.

## Settings
| Variable | Default | Meaning |
|---|---|---|
| `EVENT_BUS` | `outbox` | `kafka` sends the relay's events to Kafka |
| `KAFKA_BOOTSTRAP` | none | comma-separated `host:port`, required with `kafka` |
| `KAFKA_CLIENT_ID` | `gap-platform` | client id |
| `KAFKA_GROUP_ID` | `gap-platform` | consumer group |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `SSL`, `SASL_PLAINTEXT` or `SASL_SSL` |
| `KAFKA_SASL_MECHANISM`, `KAFKA_SASL_USERNAME`, `KAFKA_SASL_PASSWORD` | none | all three are required for a SASL protocol. Set them in the environment only |
| `KAFKA_MAX_ATTEMPTS` | 5 | tries before the dead-letter topic |
| `KAFKA_RETRY_BACKOFF_SECONDS` | 0.5 | pause between tries |
| `KAFKA_REQUEST_TIMEOUT_SECONDS` | 10 | one request to the broker |
| `KAFKA_SEND_TIMEOUT_SECONDS` | 15 | a whole send with its acknowledgement. The relay holds a row lock meanwhile, so keep it short |

The producer uses `acks=all` and is idempotent. These are not settings.

## Operate
- **Per-tenant order.** The key is the tenant id, so a tenant's events stay in order. There is no order between tenants. Do not repartition a topic that has data without thinking about this: a tenant can move to another partition and its old and new events then race.
- **Relay order.** The relay sends one row at a time. For a tenant it stops at its first failed or locked row, so a later row never overtakes it. A row past `OUTBOX_MAX_ATTEMPTS` is left for an operator and later rows of that tenant then go past it.
- **A failed dead-letter send or commit** does not lose the record: the consumer seeks back to it and reads it again.
- **Duplicates.** Delivery is at least once. A relay killed after Kafka acknowledged and before the row was marked sends the event again. A consumer must dedupe by CloudEvent id. Wrap a handler in `IdempotentConsumer` or use `KafkaEventBus.consume`, which does it with `processed_events`.
- **A message in a dead-letter topic.** Read the headers: `x-error` has the exception class and `x-error-code` says `handler_failed` or `decode_failed` (the message is left out on purpose, it may hold input text or a secret; the cause is in the consumer's log by event id), `x-original-topic`, `x-original-partition` and `x-original-offset` say where it came from, `x-attempts` how often it was tried. Fix the cause, then publish the record again to its topic by hand. The id is the same, so a consumer that did handle it once will skip it.
- **Lag.** `rpk group describe gap-platform` shows the lag per partition. The outbox side is `outbox_lag_seconds` in `/metrics`.
- **Switch back.** Set `EVENT_BUS=outbox` and restart the relay. There is no migration. Events that Kafka did not get stay in the outbox and go to the in-process bus. Events already in Kafka stay there.
- **Secrets.** Never put the SASL password in a file in the repo or in a log. `Settings` holds it as a secret value, and an error names the variable only.

## Pinned versions
- `aiokafka` `==0.14.0` (Apache-2.0), in `pyproject.toml`.
- Pin the image by digest when you first pull it (the compose file pins the tag only). Redpanda image `redpandadata/redpanda:v24.2.7`, image id `sha256:82a69763bef8d8b55ea5a520fa1b38f993908ef68946819ca1aed43541824c48` (as pulled in the Sprint 010 build).
- Redpanda is for local and test use here. The Redpanda broker's licence was not reviewed in this sprint (the adapter itself only needs the Kafka protocol, so another broker works). See `planning/QUESTIONS.md`.
