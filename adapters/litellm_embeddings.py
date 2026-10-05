"""Embeddings through LiteLLM, with an ordered fallback list (moved from `core/clients/embeddings.py`).

The primary model is tried first, then each fallback in order. A provider whose vectors have another width than
the active dimension is refused and logged (fail closed: never mix widths), and the next one is tried. If none
works the call raises, so callers deny rather than store or compare wrong vectors.
"""
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import litellm
import numpy as np

from ports.embeddings import EmbeddingDimensionMismatch, EmbeddingError, Embeddings

logger = logging.getLogger("adapters.embeddings")

# Models whose native output is wider than the active dimension and which accept a `dimensions` request
# parameter to truncate it.
#
# gemini-embedding-001 is a Matryoshka model: it emits 3072 floats natively, with the most significant signal
# packed into the leading dimensions. Asking for 768 returns that prefix, which keeps us compatible with the
# VECTOR(768) column without a re-ingest. Google's guidance is to renormalize the truncated slice, because only
# the full-width vector is unit-norm.
#
# Ollama and Azure are deliberately absent: nomic-embed-text is 768 natively, and the Azure deployment is called
# with its own dimensions setting.
_TRUNCATING_MODELS = ("gemini/gemini-embedding",)

# (model, texts, **kwargs) -> a litellm-shaped response with `.data[i]["embedding"]`.
EmbedCall = Callable[..., Awaitable[Any]]


def _truncates(model: str) -> bool:
    return model.startswith(_TRUNCATING_MODELS)


def _renormalize(vector: list[float]) -> list[float]:
    """Scale a truncated Matryoshka vector back to unit length.

    Cosine similarity is scale-invariant, so this does not change retrieval ranking in pgvector or RediSearch.
    It matters because MIN_VECTOR_SCORE and the semantic-cache threshold are absolute cutoffs.
    """
    arr = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return vector
    out: list[float] = (arr / norm).tolist()
    return out


class LitellmEmbeddings:
    def __init__(self, model: str, dim: int, fallbacks: Sequence[str] = (), call: EmbedCall | None = None) -> None:
        self._model = model
        self._dim = dim
        self._fallbacks = list(fallbacks)
        self._call = call

    @property
    def active_model(self) -> str:
        return self._model

    @property
    def active_dim(self) -> int:
        return self._dim

    async def _embed_with(self, model: str, texts: list[str]) -> list[list[float]]:
        kwargs = {"dimensions": self._dim} if _truncates(model) else {}
        # `litellm.aembedding` is looked up per call so the network guard (and tests) can replace it.
        call = self._call or litellm.aembedding
        response = await call(model=model, input=texts, **kwargs)
        vectors = [d["embedding"] for d in response.data]
        if _truncates(model):
            vectors = [_renormalize(v) for v in vectors]
        return vectors

    async def embed(self, texts: list[str]) -> Embeddings:
        if not texts:
            return Embeddings(vectors=[], model=self._model, dim=self._dim)
        refused: list[str] = []
        failed: list[str] = []
        for model in [self._model, *self._fallbacks]:
            try:
                vectors = await self._embed_with(model, texts)
            except Exception as exc:
                logger.warning("embedding provider failed: model=%s error=%s", model, type(exc).__name__)
                failed.append(model)
                last: Exception = exc
                continue
            widths = {len(v) for v in vectors}
            if widths != {self._dim}:
                logger.error(
                    "embedding provider refused: model=%s returned width %s, the active dimension is %d",
                    model, sorted(widths), self._dim,
                )
                refused.append(model)
                continue
            if model != self._model:
                logger.warning("embedding fallback used: primary=%s fallback=%s", self._model, model)
            return Embeddings(vectors=vectors, model=model, dim=self._dim)
        if refused:
            raise EmbeddingDimensionMismatch(
                f"no embedding provider returned {self._dim}-wide vectors (refused: {', '.join(refused)})"
            )
        if len(failed) == 1:
            raise last  # one provider, no fallback: surface its own error, as before the port existed
        raise EmbeddingError(f"every embedding provider failed ({', '.join(failed)})") from last
