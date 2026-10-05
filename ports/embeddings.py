"""Embedding port. Every vector carries the model and dimension that produced it."""
from dataclasses import dataclass
from typing import Protocol


class EmbeddingError(Exception):
    """No configured provider could embed the texts."""


class EmbeddingDimensionMismatch(EmbeddingError):
    """A provider returned vectors of another width than the active dimension. Refused (fail closed)."""


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    model: str
    dim: int


class EmbeddingPort(Protocol):
    @property
    def active_model(self) -> str:
        """The configured primary model: the one retrieval compares against."""
        ...

    @property
    def active_dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> Embeddings:
        """Embed a batch. `Embeddings.model` is the model that actually answered (a fallback, if the primary failed)."""
        ...
