async def bulk_insert(conn, batch):
    records = [("unknown", chunk, embedding, None) for chunk, embedding in batch]
    await conn.copy_records_to_table(
        'documents',
        records=records,
        columns=['document_id', 'content', 'embedding', 'metadata']
    )