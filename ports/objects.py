"""Object store port: content-addressed, immutable bytes. The key is the SHA-256 of the content."""
from typing import Protocol


class ObjectNotFound(KeyError):
    """No object under this key."""


class ObjectStore(Protocol):
    async def put(self, data: bytes) -> str:
        """Store the bytes and return their SHA-256 hex key. Writing the same bytes again writes nothing."""
        ...

    async def get(self, key: str) -> bytes:
        """The bytes under `key`. Raises `ObjectNotFound`."""
        ...

    async def exists(self, key: str) -> bool: ...
