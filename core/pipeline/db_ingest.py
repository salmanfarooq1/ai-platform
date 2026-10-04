import time
from collections.abc import Iterable
from itertools import islice
from pathlib import Path
from typing import Generator
from uuid import UUID

from asyncpg import Pool

from core.database import bulk_insert, create_pool
from core.database.tenant import tenant_connection
from core.ingestion.chunkers import ChunkRecord, get_chunker
from core.ingestion.embedders import embed_chunks


def batch_generator(iterable: Iterable, batch_size: int = 50) -> Generator[list, None, None]:
    '''
    Yield fixed-size batches from any iterable.

    islice() reads from a lazy generator without materializing it.
    iter() before the loop ensures batches are sequential, each call increments the same shared position, not re-read from start.
    '''
    iterator = iter(iterable)

    while True:
        sliced = islice(iterator, batch_size)   # read next batch_size items from shared position
        batch = list(sliced)                    # materialize only this batch — not the whole stream
        if not batch:                           # empty batch means the iterator is exhausted
            break
        yield batch



async def ingestion_pipeline(
    input_file_path: str,
    document_id: str,
    namespace: str = "default",
    batch_size: int = 50,
    pool: Pool = None,       # API passes its shared pool; standalone runs create one
    source_filename: str | None = None,  # real upload name; the temp path name is useless for citations
    *,
    tenant_id: UUID,         # owner of the rows; always the authenticated principal's tenant
) -> dict:
    '''
    Chunk → embed → bulk insert into PostgreSQL.

    Accepts an external pool so the API's shared pool is reused across requests.
    If no pool is passed, creates one locally — preserves standalone script usage.
    '''
    start_time = time.perf_counter()

    # Read full file text first so we can use it for content sniffing if the extension is missing/wrong
    text = Path(input_file_path).read_text(encoding="utf-8")

    # Resolve chunker from file extension (with text fallback) — dispatch table in chunkers.py
    ext = Path(input_file_path).suffix.lstrip(".")
    chunker = get_chunker(ext, text=text)

    chunks: list[ChunkRecord] = chunker(text, source=input_file_path)

    for chunk in chunks:
        chunk.metadata["source_filename"] = source_filename or Path(input_file_path).name

    total_chunks = 0
    owns_pool = pool is None

    if owns_pool:
        pool = await create_pool()

    for batch in batch_generator(chunks, batch_size):
        embedded_batch = await embed_chunks(batch)
        async with tenant_connection(pool, tenant_id) as conn:
            await bulk_insert(conn, embedded_batch, document_id=document_id, namespace=namespace, tenant_id=tenant_id)
        total_chunks += len(embedded_batch)

    if owns_pool:
        await pool.close()

    elapsed_time = time.perf_counter() - start_time

    return {
        'total_chunks': total_chunks,
        'total_time_seconds': round(elapsed_time, 3),
        'throughput_chunks_per_second': round(total_chunks / elapsed_time, 2) if elapsed_time > 0 else 0,
    }
