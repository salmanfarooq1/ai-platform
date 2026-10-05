"""One contract for every `CachePort`: the Redis adapter (real Redis Stack) and the in-memory fake."""
from uuid import uuid4

import pytest

from adapters.redis_cache import RedisCache
from ports import CacheUnavailable
from tests import harness
from tests.fakes import FakeCache, fake_embedding

A, B = uuid4(), uuid4()
QUERY = "breach notification supervisory authority 72 hours"
NEAR = "breach notification supervisory authority 72 hours please"
FAR = "quarterly marketing budget forecast"
MODEL = "test/model"


@pytest.fixture(params=["redis", "fake"])
async def cache(request):
    if request.param == "fake":
        yield FakeCache()
        return
    request.getfixturevalue("clean_state")  # a clean test Redis (skips with a reason when it is down)
    adapter = RedisCache(harness.REDIS_URL, 768)
    await adapter.ensure_semantic_index()
    try:
        yield adapter
    finally:
        await adapter.close()


async def test_get_set_round_trip_and_a_miss_is_none(cache):
    assert await cache.get("contract:missing") is None
    await cache.set("cache:contract:k", "value", ttl=60)
    assert await cache.get("cache:contract:k") == "value"
    await cache.set("cache:contract:k", "newer", ttl=60)
    assert await cache.get("cache:contract:k") == "newer"


async def test_incr_counts_and_the_counter_reads_back_as_a_string(cache):
    assert [await cache.incr("rl:contract:c", ttl=60) for _ in range(3)] == [1, 2, 3]
    assert await cache.incr("rl:contract:c", 10, ttl=60) == 13
    assert await cache.get("rl:contract:c") == "13"
    assert await cache.incr("budget:contract:c", 250, ttl=100) == 250  # the first call may be bigger than 1


async def test_delete_and_expire_never_fail_on_a_missing_key(cache):
    await cache.set("cache:contract:d", "x", ttl=60)
    await cache.expire("cache:contract:d", 120)
    await cache.delete("cache:contract:d")
    assert await cache.get("cache:contract:d") is None
    await cache.delete("cache:contract:never")
    await cache.expire("cache:contract:never", 5)


async def test_ping_succeeds_on_a_live_cache(cache):
    await cache.ping()


async def _store(cache, tenant=A, namespace="legal", text=QUERY, response='{"answer": "A"}', model=MODEL, mode="hybrid", rerank=False, top_k=5):
    await cache.semantic_store(tenant, namespace, fake_embedding(text), response, query=text, embedding_model=model,
                               retrieval_mode=mode, rerank=rerank, top_k=top_k, ttl=60)


async def _lookup(cache, tenant=A, namespace="legal", text=QUERY, model=MODEL, mode="hybrid", rerank=False, top_k=5, floor=0.65):
    return await cache.semantic_lookup(tenant, namespace, fake_embedding(text), embedding_model=model, retrieval_mode=mode,
                                       rerank=rerank, top_k=top_k, min_similarity=floor)


async def test_semantic_lookup_finds_a_near_duplicate_and_not_an_unrelated_query(cache):
    await _store(cache)
    hit = await _lookup(cache, text=NEAR)
    assert hit is not None and hit.response == '{"answer": "A"}' and hit.query == QUERY
    assert 0.65 <= hit.similarity <= 1.0001
    assert await _lookup(cache, text=FAR) is None
    assert await _lookup(cache, text=NEAR, floor=0.9999) is None  # the floor is the caller's


@pytest.mark.parametrize("change", [
    {"tenant": B}, {"namespace": "kyc_aml"}, {"model": "test/other"}, {"mode": "bm25_only"}, {"rerank": True}, {"top_k": 6},
])
async def test_semantic_lookup_is_isolated_by_every_filter(cache, change):
    await _store(cache)
    assert await _lookup(cache, text=QUERY) is not None  # sanity: the owner hits
    assert await _lookup(cache, text=QUERY, **change) is None


async def test_the_semantic_cache_is_per_tenant_for_the_same_query(cache):
    await _store(cache, tenant=A, response='{"answer": "from A"}')
    await _store(cache, tenant=B, response='{"answer": "from B"}')
    assert (await _lookup(cache, tenant=A, text=NEAR)).response == '{"answer": "from A"}'
    assert (await _lookup(cache, tenant=B, text=NEAR)).response == '{"answer": "from B"}'


async def test_a_cache_that_cannot_be_reached_raises_cache_unavailable():
    """The port's failure mode: callers degrade (cache) or deny (limits) on this one exception type."""
    for broken in (RedisCache("redis://127.0.0.1:1/0", 768), FakeCache(fail_with=CacheUnavailable("down"))):
        with pytest.raises(CacheUnavailable):
            await broken.get("k")
        with pytest.raises(CacheUnavailable):
            await broken.set("k", "v", ttl=1)
        with pytest.raises(CacheUnavailable):
            await broken.incr("k", ttl=1)
        with pytest.raises(CacheUnavailable):
            await broken.ping()
        with pytest.raises(CacheUnavailable):
            await _lookup(broken)
        with pytest.raises(CacheUnavailable):
            await _store(broken)
