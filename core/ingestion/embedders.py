from core.ingestion.chunkers import ChunkRecord
from ports import EmbeddingPort


async def embed_chunks(embeddings: EmbeddingPort, chunks: list[ChunkRecord]) -> tuple[list[ChunkRecord], str, int]:
    '''
    Send a batch of chunks to the embedding port and fill their embedding fields.

    Returns the chunks and the model and dimension that produced the vectors (a fallback model, if the primary
    failed), so the rows can record their provenance.
    '''
    if not chunks:
        return [], embeddings.active_model, embeddings.active_dim

    result = await embeddings.embed([chunk.content for chunk in chunks])

    for chunk, embedding in zip(chunks, result.vectors):
        chunk.embedding = embedding

    return chunks, result.model, result.dim
