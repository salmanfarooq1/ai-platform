import litellm
from core.ingestion.chunkers import ChunkRecord
from config import LLM_CONFIG

async def embed_chunks(chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    '''
    Send a batch of chunks to the AI via LiteLLM and fill their embedding fields.
    Uses the embedding model defined in config.py based on the deployment MODE.
    '''
    if not chunks:
        return []

    texts = [chunk.content for chunk in chunks]

    # Dynamically grab the model (e.g., ollama/nomic-embed-text or azure/...)
    target_model = LLM_CONFIG["embedding_model"]

    # Make a single async batch request
    response = await litellm.aembedding(
        model=target_model,
        input=texts
    )

    for i, data in enumerate(response.data):
        chunks[i].embedding = data["embedding"]

    return chunks