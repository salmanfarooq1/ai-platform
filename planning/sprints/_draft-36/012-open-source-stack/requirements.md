# Sprint 012: Open-source stack. Requirements

Infrastructure, Kernel. Compose, CI services, the cache adapter and verify scripts. No API, schema or UI change.

## Scope
1. Valkey replaces Redis Stack.
   - `valkey/valkey-bundle:9.1.3` (Valkey 9.1.2, valkey-search 1.2.1) in compose and in CI (`tests.yml`, `frontend.yml`).
   - `adapters/redis_cache.py`: match "already exists" (Valkey says "Index <name> in database 0 already exists"); drop the unsearched TEXT fields `response` and `query`, and `SORTBY` (KNN is already sorted). A test proves `RETURN` still fetches the unindexed fields. New volume name.
   - The cache contract suite stays green. A pgvector cache adapter is written only as a documented fallback if the spike fails.
2. Apache Kafka replaces Redpanda.
   - `apache/kafka:4.3.1` (KRaft) in the profile, renamed `cdc`.
   - The Kafka tests and `scripts/verify/kafka.sh` pass on it.
3. Object store.
   - SeaweedFS `chrislusf/seaweedfs:4.47` in a `lake` profile, with a bucket-init job.
   - `scripts/verify/seaweedfs.sh` replaces `scripts/verify/minio.sh`. Presigned URLs tested with boto3.
   - The skip allowlist is updated.
4. Runtime.
   - Document Docker Engine (moby) inside WSL, or Podman, as the supported runtime.
   - `scripts/preflight.sh` checks the engine, memory, clock and ports.
   - `.wslconfig` guidance: `memory=`, `autoMemoryReclaim=gradual`.
5. Compose.
   - Bind every published port to `127.0.0.1`.
   - Healthchecks: `pg_isready`, `valkey-cli ping`, `ollama list`, the S3 port. `depends_on: condition: service_healthy`.
   - Ollama moves to a `models` profile.
   - One-shot init jobs: bucket, topics, model pull.

## Out of scope
- Choosing and locking the local models (014). The model-pull job pulls the embedding model only.
- Kafka SASL, ACLs and Debezium (020). Any consumer of Kafka.
- Per-tenant SeaweedFS identities (016).

## Nav placement
No UI change.

## Questions this sprint closes
- Q42: Redpanda (BSL) is replaced by Apache Kafka.
- Q45: topic retention defaults are written in `docs/operations.md` and set by the topic job.
- Q46: carried from 011; the Kafka setting names are confirmed against the new profile.
- Q20: only if the stale-vector count is touched while moving to Valkey. Otherwise it stays open.
