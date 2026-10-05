"""One contract for every `ObjectStore`: local filesystem, the S3 adapter over a fake client, and a live MinIO.

The live MinIO run needs `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` and `MINIO_BUCKET` (see
scripts/verify/minio.sh). Without them that parameter is skipped with a reason: the image could not be pulled here.
"""
import hashlib
import os

import pytest

from adapters.local_object_store import LocalObjectStore
from adapters.s3_object_store import S3ObjectStore
from ports import ObjectNotFound
from tests.fakes import FakeS3Client

MINIO = ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET")


class Harness:
    """The store under test and a way to count how many times bytes were really written."""

    def __init__(self, store, writes):
        self.store, self.writes = store, writes


def _local(tmp_path):
    root = tmp_path / "objects"
    return Harness(LocalObjectStore(root), lambda: len([p for p in root.rglob("*") if p.is_file()]))


def _s3_fake(tmp_path):
    client = FakeS3Client()
    return Harness(S3ObjectStore("bucket", client), lambda: client.put_calls)


def _minio(tmp_path):
    missing = [name for name in MINIO if not os.environ.get(name)]
    if missing:
        pytest.skip(f"live MinIO not available here (image not pullable); set {', '.join(missing)} (scripts/verify/minio.sh)")
    store = S3ObjectStore.from_settings(
        endpoint_url=os.environ["MINIO_ENDPOINT"], bucket=os.environ["MINIO_BUCKET"],
        access_key_id=os.environ["MINIO_ACCESS_KEY"], secret_access_key=os.environ["MINIO_SECRET_KEY"], region="us-east-1",
    )
    return Harness(store, lambda: -1)  # a live bucket has no write counter: the "written once" check is skipped


@pytest.fixture(params=["local", "s3-fake-client", "minio"])
def env(request, tmp_path):
    return {"local": _local, "s3-fake-client": _s3_fake, "minio": _minio}[request.param](tmp_path)


async def test_put_returns_the_sha256_of_the_bytes_and_get_returns_them(env):
    data = b"raw regulatory text \x00\xff"
    key = await env.store.put(data)
    assert key == hashlib.sha256(data).hexdigest()
    assert await env.store.get(key) == data
    assert hashlib.sha256(await env.store.get(key)).hexdigest() == key  # strict rule 6: the hash is the address


async def test_the_same_bytes_twice_give_the_same_key_and_are_written_once(env):
    first = await env.store.put(b"same bytes")
    writes_after_first = env.writes()
    second = await env.store.put(b"same bytes")
    assert first == second
    if writes_after_first >= 0:
        assert env.writes() == writes_after_first == 1


async def test_exists_tells_stored_from_unknown(env):
    key = await env.store.put(b"present")
    assert await env.store.exists(key) is True
    assert await env.store.exists(hashlib.sha256(b"absent").hexdigest()) is False


async def test_a_missing_key_raises_object_not_found(env):
    with pytest.raises(ObjectNotFound):
        await env.store.get(hashlib.sha256(b"never stored").hexdigest())


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/path", "", "not-a-hash", "A" * 64])
async def test_a_key_that_is_not_a_sha256_is_never_found_and_never_touches_the_backend(env, bad):
    assert await env.store.exists(bad) is False
    with pytest.raises(ObjectNotFound):
        await env.store.get(bad)


async def test_different_bytes_get_different_keys_and_empty_bytes_work(env):
    a, b, empty = await env.store.put(b"a"), await env.store.put(b"b"), await env.store.put(b"")
    assert len({a, b, empty}) == 3
    assert await env.store.get(empty) == b""
    assert empty == hashlib.sha256(b"").hexdigest()
