import time
from collections.abc import Awaitable, Callable, Iterable
from itertools import islice
from pathlib import Path
from typing import Generator
from uuid import UUID

from core.ingestion.chunkers import ChunkRecord, get_chunker
from core.ingestion.embedders import embed_chunks
from ports import ChunkRow, EmbeddingPort, KnowledgeStore


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
    source_filename: str | None = None,  # real upload name; the temp path name is useless for citations
    *,
    store: KnowledgeStore,
    embeddings: EmbeddingPort,
    tenant_id: UUID,         # owner of the rows; always the authenticated principal's tenant
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,  # (chunks stored, chunks in total)
) -> dict:
    '''
    Chunk → embed → insert through the knowledge store port.

    Each row records the embedding model and dimension that produced its vector.
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
    if on_progress is not None:
        await on_progress(0, len(chunks))

    for batch in batch_generator(chunks, batch_size):
        embedded_batch, model, dim = await embed_chunks(embeddings, batch)
        if any(c.embedding is None for c in embedded_batch):
            raise RuntimeError("the embedding port returned no vector for a chunk")  # never store a row without one
        rows = [ChunkRow(content=c.content, embedding=c.embedding, metadata=c.metadata)
                for c in embedded_batch if c.embedding is not None]
        await store.insert_chunks(tenant_id, document_id, namespace, rows, embedding_model=model, embedding_dim=dim)
        total_chunks += len(embedded_batch)
        if on_progress is not None:
            await on_progress(total_chunks, len(chunks))

    elapsed_time = time.perf_counter() - start_time

    return {
        'total_chunks': total_chunks,
        'total_time_seconds': round(elapsed_time, 3),
        'throughput_chunks_per_second': round(total_chunks / elapsed_time, 2) if elapsed_time > 0 else 0,
    }
