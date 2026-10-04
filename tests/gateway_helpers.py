"""Builders for gateway tests: a principal, a boundary and an enforcement context without a database."""
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4

from core.identity.models import Principal
from gateway import EnforcementContext, GatewayRuntime
from gateway.boundary import build_boundary
from gateway.policy import PolicyDocument

TENANT = UUID("00000000-0000-0000-0000-0000000000aa")
ALL_SCOPES = ("kb:read", "kb:write", "query", "agent")


def make_principal(scopes: Iterable[str] = ALL_SCOPES, tenant: UUID = TENANT) -> Principal:
    return Principal(id=uuid4(), tenant_id=tenant, kind="service", scopes=frozenset(scopes))


class FakeRedis:
    """Just enough of redis.asyncio for the limits: incr, expire, get, incrby. `fail` makes every call raise."""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, int] = {}
        self.fail = fail

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("redis is down")

    async def incr(self, key: str) -> int:
        self._check()
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self._check()
        return True

    async def get(self, key: str) -> str | None:
        self._check()
        return str(self.store[key]) if key in self.store else None

    async def incrby(self, key: str, amount: int) -> int:
        self._check()
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]


def make_runtime(redis: FakeRedis | None = None, pool: Any = None) -> GatewayRuntime:
    client = redis or FakeRedis()

    async def get_redis() -> FakeRedis:
        return client

    return GatewayRuntime(pool=pool, get_redis=get_redis)


def make_ctx(
    scopes: Iterable[str] = ALL_SCOPES,
    policy: PolicyDocument | dict | None = None,
    version: int | None = None,
    redis: FakeRedis | None = None,
    principal: Principal | None = None,
) -> EnforcementContext:
    who = principal or make_principal(scopes)
    doc = PolicyDocument.model_validate(policy) if isinstance(policy, dict) else policy
    return EnforcementContext(
        principal=who,
        request_id="req-test",
        trace_id="trace-test",
        boundary=build_boundary(who, doc, version),
        runtime=make_runtime(redis),
    )
