from asyncpg import Connection

async def bulk_insert(conn: Connection, batch: list[tuple[str, list]]) -> None:
    '''
    COPY a batch of (chunk, embedding) tuples into the documents table.

    conn comes in from outside, keeps the pool benefit, no TCP handshake per call.
    document_id is "unknown" until real file metadata is wired in.
    '''
    # each record maps to one row: (document_id, content, embedding, metadata)
    # metadata is None for now - JSONB column will be used for source, page, etc. later
    records = [("unknown", chunk, embedding, None) for chunk, embedding in batch]

    await conn.copy_records_to_table(
        'documents',
        records = records,
        columns = ['document_id', 'content', 'embedding', 'metadata']
    )