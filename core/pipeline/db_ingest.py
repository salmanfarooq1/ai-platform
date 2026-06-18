import time
from itertools import islice
from typing import Generator, Iterator
from asyncpg import Pool
from core.ingestion.chunkers import ChunkRecord, get_chunker
from core.ingestion.embedders import embed_chunks
from core.database import create_pool, bulk_insert
from pathlib import Path


def batch_generator(iterable: Iterator, batch_size: int = 50) -> Generator[list, None, None]:
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
) -> dict:
    '''
    Chunk → embed → bulk insert into PostgreSQL.

    Accepts an external pool so the API's shared pool is reused across requests.
    If no pool is passed, creates one locally — preserves standalone script usage.
    '''
    start_time = time.perf_counter()

    # Resolve chunker from file extension — dispatch table in chunkers.py
    ext = Path(input_file_path).suffix.lstrip(".")
    chunker = get_chunker(ext)

    # Read full file text — chunkers operate on strings, not byte streams
    # This is a conscious tradeoff: chunkers need the full text to detect
    # headers, paragraph boundaries, etc. Generator streaming doesn't apply here.
    text = Path(input_file_path).read_text(encoding="utf-8")
    chunks: list[ChunkRecord] = chunker(text, source=input_file_path)

    total_chunks = 0
    owns_pool = pool is None

    if owns_pool:
        pool = await create_pool()

    for batch in batch_generator(chunks, batch_size):
        embedded_batch = await embed_chunks(batch)
        async with pool.acquire() as conn:
            await bulk_insert(conn, embedded_batch, document_id=document_id, namespace=namespace)
        total_chunks += len(embedded_batch)

    if owns_pool:
        await pool.close()

    elapsed_time = time.perf_counter() - start_time

    return {
        'total_chunks': total_chunks,
        'total_time_seconds': round(elapsed_time, 3),
        'throughput_chunks_per_second': round(total_chunks / elapsed_time, 2) if elapsed_time > 0 else 0,
    }
