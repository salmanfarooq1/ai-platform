

import json
from uuid import UUID

from asyncpg import Connection

from core.ingestion.chunkers import ChunkRecord


async def bulk_insert(
    conn: Connection,
    batch: list[ChunkRecord],
    document_id: str,
    namespace: str = "default",
    *,
    tenant_id: UUID,
) -> None:
    '''
    Insert a batch of ChunkRecords into the documents table.

    Uses a pipelined `executemany` INSERT, not COPY: Postgres refuses COPY FROM into a table with
    row-level security enabled.

    metadata dict is manually serialized to JSON string via json.dumps before COPY.
    '''
    records = [
        (
            tenant_id,
            document_id,
            namespace,
            chunk.content,
            chunk.embedding,
            json.dumps(chunk.metadata),
        )
        for chunk in batch
    ]

    await conn.executemany(
        "INSERT INTO documents (tenant_id, document_id, namespace, content, embedding, metadata) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        records,
    )
