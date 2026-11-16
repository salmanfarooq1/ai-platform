"""Embedding port. Every vector carries the model and dimension that produced it."""
from dataclasses import dataclass
from typing import Protocol

from ports.models import ResolvedModel


class EmbeddingError(Exception):
    """No configured provider could embed the texts."""


class EmbeddingDimensionMismatch(EmbeddingError):
    """A provider returned vectors of another width than the active dimension. Refused (fail closed)."""

    def __init__(self, message: str, *, expected_dim: int | None = None, returned_dim: int | None = None) -> None:
        self.expected_dim = expected_dim
        self.returned_dim = returned_dim
        super().__init__(message)


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    model: str
    dim: int
    route_fingerprint: str = ""


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

    async def embed_resolved(self, resolved: ResolvedModel, texts: list[str]) -> Embeddings:
        """Embed one batch using exactly the route carried by the catalog resolution."""
        ...
