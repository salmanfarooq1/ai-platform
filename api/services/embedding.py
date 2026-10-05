"""Embedding helpers for the request path. The provider is behind `EmbeddingPort` (see `adapters/`)."""
from ports import EmbeddingPort, Embeddings


async def embed_query(embeddings: EmbeddingPort, query: str) -> Embeddings:
    """Embed a single query string. The result carries the model and dimension that produced the vector."""
    result = await embeddings.embed([query])
    return result
