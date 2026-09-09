from core.clients.embeddings import aembed_texts
from core.ingestion.chunkers import ChunkRecord


async def embed_chunks(chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    '''
    Send a batch of chunks to the AI via LiteLLM and fill their embedding fields.
    Uses the embedding model defined in config.py based on the deployment MODE.
    '''
    if not chunks:
        return []

    texts = [chunk.content for chunk in chunks]

    # Single async batch request. The model and any provider-specific width
    # handling live in core.clients.embeddings.
    embeddings = await aembed_texts(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding

    return chunks
