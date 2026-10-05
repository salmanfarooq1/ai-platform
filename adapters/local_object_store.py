"""Object store on the local filesystem. Content-addressed: the file name is the SHA-256 of the bytes."""
import asyncio
import hashlib
import os
import re
import tempfile
from pathlib import Path

from ports.objects import ObjectNotFound

_KEY = re.compile(r"^[0-9a-f]{64}$")


def _valid(key: str) -> str:
    if not _KEY.match(key):
        raise ObjectNotFound(key)  # also keeps `../` and absolute paths out of the file system call
    return key


class LocalObjectStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root / key[:2] / key

    async def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        return await asyncio.to_thread(self._put, key, data)

    def _put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        if path.exists():
            return key  # same bytes: written once
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file and rename, so a reader never sees a half-written object.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return key

    async def get(self, key: str) -> bytes:
        path = self._path(_valid(key))
        try:
            return await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            raise ObjectNotFound(key) from None

    async def exists(self, key: str) -> bool:
        if not _KEY.match(key):
            return False
        return await asyncio.to_thread(self._path(key).exists)
