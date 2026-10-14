# Sprint 020: CDC streaming. Requirements

Infrastructure plus a small UI change, module M4 Data Plane. Adds the first real Kafka consumer.

## Scope
1. **Compose profile `cdc`.**
   - Apache Kafka (`apache/kafka:4.3.1`, from Sprint 012) with SASL/SCRAM and ACLs.
   - Debezium `quay.io/debezium/connect:3.6.2.Final`. Kafka Connect port 8083 is not published.
   - Connector secrets come through a Kafka Connect config provider, never inline.
   - The source Postgres runs with `wal_level=logical`, in the compose command and in a CI step.
2. **Source setup.**
   - A replication-only role. A publication filtered to the listed tables.
   - A Debezium heartbeat. A WAL growth alert on the replication slot.
3. **Our own sink into DuckLake.**
   - Micro-batches of 10 to 30 seconds. Dedupe by key, keeping the last change. A guard by source LSN.
   - Kafka offsets stored in the same DuckLake transaction as the data.
   - `op=d` deletes rows. The initial snapshot comes from `op=r` events.
   - An added column becomes `ALTER TABLE ... ADD COLUMN`. Any other schema change quarantines the batch.
   - The tenant comes from the connector registration, never from the message.
4. **First real Kafka consumer and open questions.**
   - Q41: the CDC sink is the first consumer. It runs as its own process, `python -m workers.cdc_sink`, compose service `cdc-sink`.
   - Q43 and Q44 decided (see blueprint). Q45 answered for CDC topics.
   - Freshness is measured from the source commit time (`ts_ms`).
5. **Freshness badge and verification.**
   - A small UI badge: freshness per dataset.
   - `scripts/verify/cdc.sh` for the live stack. A fake CDC event source for pytest.
   - ADR-0017.

## Out of scope
- Re-embedding stale vectors (moved out of this sprint).
- CDC sources other than the reference source database. Kafka TLS. Freshness SLOs and quality states (022).
- Lineage events from CDC (025).

## Nav placement
Data > Datasets: a freshness badge on each row and on the dataset detail.

## Questions this sprint closes
- Q41: which consumer comes first, and which process runs it.
- Q43: the topic list for wildcard consumers.
- Q44: retry counts across consumer restarts.
- Q45: Kafka topic retention (for CDC topics; platform topics noted).
