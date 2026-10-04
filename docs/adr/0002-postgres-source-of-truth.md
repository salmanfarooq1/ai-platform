# ADR 0002: Postgres as the source of truth

**Status:** Accepted

## Context
- Documents, vectors (pgvector) and usage already live in Postgres (`core/database/schema.sql`). Redis holds caches.
- The coming work needs a queue, audit receipts, policy data and workflow state.

## Decision
- **Postgres holds all durable truth:** tenants, documents, vectors, the job queue, receipts, policy data and workflow state.
- Redis and DuckDB hold **derived** data only, so they can be rebuilt from Postgres.
- Raw uploaded files go to object storage, addressed by their content hash, and are never changed.
- Schema changes only go through versioned, forward-only migrations (Alembic, Sprint 002).

## Consequences
- There is one backup and restore point, and joins and transactions span all core data.
- Losing Redis is a performance event, not data loss.
- Postgres load must be watched. A store moves out only when measured load requires it.

## Alternatives considered
- **A dedicated vector database:** an extra service and cost. pgvector covers the current scale.
- **Kafka or Redis Streams as the queue now:** not needed at this scale. Postgres `SKIP LOCKED` is enough.
