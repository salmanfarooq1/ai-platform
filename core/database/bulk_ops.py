
import json
from asyncpg import Connection
from core.ingestion.chunkers import ChunkRecord

async def bulk_insert(conn: Connection, batch: list[ChunkRecord], document_id: str, namespace: str = "default") -> None:
    '''
    COPY a batch of ChunkRecords into the documents table.
    
    metadata dict serialized to JSON string — asyncpg expects a string
    for JSONB columns, not a Python dict.
    '''
    records = [
        (
            document_id,
            namespace,
            chunk.content,
            chunk.embedding,
            json.dumps(chunk.metadata),
        )
        for chunk in batch
    ]

    await conn.copy_records_to_table(
        'documents',
        records=records,
        columns=['document_id', 'namespace', 'content', 'embedding', 'metadata']
    )