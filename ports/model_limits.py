"""Port for the Valkey-backed model circuit breaker and tenant leases."""

from enum import Enum
from typing import Protocol, runtime_checkable
from uuid import UUID

from ports.cache import CacheUnavailable


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    TRIAL = "trial"


@runtime_checkable
class ModelLimitStore(Protocol):
    """Atomic model route breaker and per-tenant concurrency lease operations."""

    async def check_breaker(self, fingerprint: str) -> BreakerState: ...

    async def record_success(self, fingerprint: str) -> None: ...

    async def record_failure(self, fingerprint: str) -> None: ...

    async def release_trial(self, fingerprint: str) -> None: ...

    async def acquire_lease(self, tenant_id: UUID) -> str | None: ...

    async def release_lease(self, tenant_id: UUID, lease_id: str) -> None: ...


__all__ = ["BreakerState", "ModelLimitStore", "CacheUnavailable"]
