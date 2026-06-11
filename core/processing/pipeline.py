"""
core/processing/pipeline.py
=============================
Async pipeline step: read a file, select the right chunker for its type,
run chunking in the process pool, return list[ChunkRecord] ready for embedding.

This is the function that Week 5's FastAPI /ingest route handler will call:

    @router.post("/ingest")
    async def ingest(file: UploadFile, ...):
        text   = (await file.read()).decode()
        chunks = await chunk_document(text, source=file.filename)
        # embed + store follows here

WHY THE SPLIT BETWEEN pipeline.py AND db_ingest.py:
  core/pipeline/db_ingest.py (Week 3): end-to-end script pipeline — reads a
    file path, cleans, embeds with fake embeddings, bulk-writes to DB. Designed
    to run as a standalone script for testing the full plumbing.

  core/processing/pipeline.py (Week 4): single async step — takes text that's
    already in memory, dispatches to the right chunker, offloads the CPU work.
    Designed to be composed inside an HTTP handler where the file is received
    over the network, not read from disk.

  They coexist. Week 5 builds on this file; Week 3 script stays as a benchmark
  reference.
"""

from pathlib import Path

from core.ingestion.chunkers import ChunkRecord, get_chunker
from core.processing.cpu_offload import run_cpu_bound


async def chunk_document(
    text:   str,
    source: str | Path,
) -> list[ChunkRecord]:
    """
    Select the correct chunker for source's file extension and run it in
    the process pool so the event loop is not blocked.

    Extension dispatch (via CHUNKER_REGISTRY in core/ingestion/chunkers.py):
        .txt  → recursive_split        (paragraph → sentence → character)
        .md   → header_aware_split     (# / ## / ### boundaries)
        .json → chunk_openapi_spec     (one HTTP operation = one chunk)
        .pdf  → NotImplementedError    (Week 13 — Docling multimodal)

    Args:
        text:   Full document text, already decoded to str.
        source: Original filename or path — used for:
                  1. Extension detection (which chunker to use)
                  2. Stored in every ChunkRecord's metadata.source field
                     so retrieval results can cite the origin document.

    Returns:
        list[ChunkRecord] — each record has:
            .content   str             the chunk text (ready to embed)
            .metadata  dict            citation + position + chunker config
            .embedding None            filled by embedders.py downstream

    Raises:
        ValueError          — unrecognised file extension
        NotImplementedError — known extension not yet implemented (e.g. .pdf)
        ValueError          — invalid JSON when source is .json OpenAPI spec

    Example:
        chunks = await chunk_document(readme_text, source="README.md")
        chunks = await chunk_document(spec_json,   source="openapi.json")
    """
    ext     = Path(source).suffix          # e.g. ".md", ".json", ".txt"
    chunker = get_chunker(ext)             # raises ValueError / NotImplementedError early

    # Offload to process pool — chunking is CPU work, never call inline in async
    return await run_cpu_bound(chunker, text, str(source))
