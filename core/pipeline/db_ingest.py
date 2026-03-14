import time
from itertools import islice
from typing import Generator, Iterator
from asyncpg import Pool
from core.ingestion import read_chunks, clean_chunks, embed_chunks
from core.database import create_pool, bulk_insert


def batch_generator(iterable: Iterator, batch_size: int = 50) -> Generator[list, None, None]:
    '''
    Yield fixed-size batches from any iterable.

    islice() reads from a lazy generator without materializing it.
    iter() before the loop ensures batches are sequential, each call advances the same shared position, not re-read from start.
    '''
    iterator = iter(iterable)

    while True:
        sliced = islice(iterator, batch_size)   # read next batch_size items from shared position
        batch = list(sliced)                    # materialize only this batch — not the whole stream
        if not batch:                           # empty batch means the iterator is exhausted
            break
        yield batch


async def ingestion_pipeline(input_file_path: str, batch_size: int = 50) -> dict:
    '''
    Read a file, clean and embed chunks, bulk-write to PostgreSQL.

    Week 2 called an HTTP API and wrote to JSONL.
    This version: embeddings generated in-process, storage via COPY to PostgreSQL.

    Pool is created once per run, connection cost paid once, reused across all batches.
    batch_size=50 is a RAM vs round-trip tradeoff.
    '''
    start_time = time.perf_counter()

    # Week 1 generators, memory stays flat regardless of file size
    chunks = read_chunks(input_file_path, chunk_size=1024)
    cleaned_chunks = clean_chunks(chunks)

    total_chunks = 0

    # create pool once, all batches share the same set of live connections
    pool: Pool = await create_pool()

    for batch in batch_generator(cleaned_chunks, batch_size):
        # embed_chunks returns (chunk, embedding) tuples, one per chunk in the batch
        embedding_tuple_list = list(embed_chunks(batch))

        # acquire borrows a connection from the pool and returns it automatically on exit
        # this means no connection overhead per batch, pool keeps connections alive
        async with pool.acquire() as conn:
            await bulk_insert(conn, embedding_tuple_list)

        total_chunks += len(embedding_tuple_list)

    await pool.close()  # release all connections cleanly, important in scripts, less so in long-running servers

    elapsed_time = time.perf_counter() - start_time

    return {
        'total_chunks': total_chunks,
        'total_time_seconds': round(elapsed_time, 3),
        'throughput_chunks_per_second': round(total_chunks / elapsed_time, 2)
    }