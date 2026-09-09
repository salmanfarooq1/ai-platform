"""
core/clients/embeddings.py

The single entry point for every embedding call in the platform: ingestion,
the semantic cache, and the /health probe all route through aembed_texts().

Consolidating them here means provider quirks are handled once. The quirk that
forced this module into existence is Gemini's output width — see below.
"""
import litellm
import numpy as np

from config import EMBEDDING_DIM, LLM_CONFIG

# Models whose native output is wider than EMBEDDING_DIM and which accept a
# `dimensions` request parameter to truncate it.
#
# gemini-embedding-001 is a Matryoshka model: it emits 3072 floats natively,
# with the most significant signal packed into the leading dimensions. Asking
# for 768 returns that prefix, which keeps us compatible with the VECTOR(768)
# column in schema.sql without a re-ingest. Google's guidance is to renormalize
# the truncated slice, because only the full-width vector is unit-norm.
#
# Ollama and Azure are deliberately absent: nomic-embed-text is 768 natively,
# and the Azure deployment is called with its own dimensions setting.
_TRUNCATING_MODELS = ("gemini/gemini-embedding",)


def _truncates(model: str) -> bool:
    return model.startswith(_TRUNCATING_MODELS)


async def aembed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of strings with the mode's configured embedding model.

    Always returns EMBEDDING_DIM-wide vectors, whatever the provider's native
    width. Raises whatever LiteLLM raises — callers decide how to degrade.
    """
    if not texts:
        return []

    model = LLM_CONFIG["embedding_model"]
    kwargs = {"dimensions": EMBEDDING_DIM} if _truncates(model) else {}

    response = await litellm.aembedding(model=model, input=texts, **kwargs)
    vectors = [d["embedding"] for d in response.data]

    if _truncates(model):
        vectors = [_renormalize(v) for v in vectors]

    return vectors


def _renormalize(vector: list[float]) -> list[float]:
    """
    Scale a truncated Matryoshka vector back to unit length.

    Cosine similarity is scale-invariant, so this does not change retrieval
    ranking in pgvector or RediSearch. It matters because MIN_VECTOR_SCORE and
    the semantic-cache threshold are absolute cutoffs, and because vectors
    stored at inconsistent magnitudes are a trap for anything added later that
    assumes unit norm (dot-product indexes, for one).
    """
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return vector
    return (arr / norm).tolist()
