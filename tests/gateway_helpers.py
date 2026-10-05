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
    """A `CachePort` for the gateway limits (get, incr, expire, set, delete). `fail` makes every call raise."""

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, int] = {}
        self.fail = fail

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("redis is down")

    async def get(self, key: str) -> str | None:
        self._check()
        return str(self.store[key]) if key in self.store else None

    async def set(self, key: str, value: str, *, ttl: int) -> None:
        self._check()
        self.store[key] = int(value)

    async def incr(self, key: str, amount: int = 1, *, ttl: int | None = None) -> int:
        self._check()
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> None:
        self._check()

    async def delete(self, key: str) -> None:
        self._check()
        self.store.pop(key, None)


def make_runtime(redis: FakeRedis | None = None, pool: Any = None) -> GatewayRuntime:
    return GatewayRuntime(pool=pool, cache=redis or FakeRedis())


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
