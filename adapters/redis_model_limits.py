"""Atomic model breaker and concurrency leases implemented with Valkey Lua scripts."""

from typing import Any
from uuid import UUID, uuid4

from redis.exceptions import RedisError

from ports.cache import CacheUnavailable
from ports.model_limits import BreakerState, ModelLimitStore

_CHECK_BREAKER = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local failures = tonumber(redis.call('GET', KEYS[1]) or '0')
local opened_until = tonumber(redis.call('GET', KEYS[2]) or '0')
if failures < tonumber(ARGV[1]) then return 1 end
if opened_until > now then return 0 end
if redis.call('SET', KEYS[3], '1', 'NX', 'PX', ARGV[2]) then return 2 end
return 0
"""

_RECORD_FAILURE = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local failures = redis.call('INCR', KEYS[1])
redis.call('PEXPIRE', KEYS[1], ARGV[1])
if failures >= tonumber(ARGV[2]) then
  redis.call('SET', KEYS[2], now + tonumber(ARGV[3]), 'PX', ARGV[1])
end
redis.call('DEL', KEYS[3])
return failures
"""

_RECORD_SUCCESS = "return redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])"
_RELEASE_TRIAL = "return redis.call('DEL', KEYS[1])"

_ACQUIRE_LEASE = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then return 0 end
redis.call('ZADD', KEYS[1], now + tonumber(ARGV[2]), ARGV[3])
redis.call('PEXPIRE', KEYS[1], ARGV[2])
return 1
"""
_RELEASE_LEASE = "return redis.call('ZREM', KEYS[1], ARGV[1])"


class RedisModelLimitStore(ModelLimitStore):
    """Store using the Redis command client shared with ``RedisCache``."""

    def __init__(
        self,
        client: Any,
        *,
        max_concurrent_per_tenant: int,
        failure_threshold: int,
        open_seconds: float,
        lease_ttl_seconds: float,
    ) -> None:
        self._client = client
        self._max_concurrent = max_concurrent_per_tenant
        self._failure_threshold = failure_threshold
        self._open_ms = max(1, int(open_seconds * 1000))
        self._lease_ttl_ms = max(1, int(lease_ttl_seconds * 1000))
        self._breaker_ttl_ms = max(self._open_ms + self._lease_ttl_ms, 1000)

    @staticmethod
    def _breaker_keys(fingerprint: str) -> tuple[str, str, str]:
        prefix = f"cache:model:breaker:{fingerprint}"
        return f"{prefix}:failures", f"{prefix}:open_until", f"{prefix}:trial"

    @staticmethod
    def _lease_key(tenant_id: UUID) -> str:
        return f"cache:model:leases:{tenant_id}"

    async def _eval(self, script: str, keys: list[str], *args: str) -> Any:
        try:
            return await self._client.eval(script, len(keys), *keys, *args)
        except RedisError as exc:
            raise CacheUnavailable("model limit store unavailable") from exc

    async def check_breaker(self, fingerprint: str) -> BreakerState:
        failures, opened_until, trial = self._breaker_keys(fingerprint)
        result = int(await self._eval(
            _CHECK_BREAKER, [failures, opened_until, trial],
            str(self._failure_threshold), str(self._lease_ttl_ms),
        ))
        return {0: BreakerState.OPEN, 1: BreakerState.CLOSED, 2: BreakerState.TRIAL}[result]

    async def record_success(self, fingerprint: str) -> None:
        await self._eval(_RECORD_SUCCESS, list(self._breaker_keys(fingerprint)))

    async def record_failure(self, fingerprint: str) -> None:
        failures, opened_until, trial = self._breaker_keys(fingerprint)
        await self._eval(
            _RECORD_FAILURE, [failures, opened_until, trial], str(self._breaker_ttl_ms),
            str(self._failure_threshold), str(self._open_ms),
        )

    async def release_trial(self, fingerprint: str) -> None:
        await self._eval(_RELEASE_TRIAL, [self._breaker_keys(fingerprint)[2]])

    async def acquire_lease(self, tenant_id: UUID) -> str | None:
        lease_id = uuid4().hex
        acquired = int(await self._eval(
            _ACQUIRE_LEASE, [self._lease_key(tenant_id)], str(self._max_concurrent),
            str(self._lease_ttl_ms), lease_id,
        ))
        return lease_id if acquired else None

    async def release_lease(self, tenant_id: UUID, lease_id: str) -> None:
        await self._eval(_RELEASE_LEASE, [self._lease_key(tenant_id)], lease_id)
