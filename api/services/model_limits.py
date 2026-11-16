"""Pure orchestration for model breaker checks and tenant leases."""

from dataclasses import dataclass
from uuid import UUID

from gateway.types import ModelLimitOutcome
from ports.model_limits import BreakerState, ModelLimitStore
from ports.models import ResolvedModel


@dataclass(frozen=True)
class ModelLimitCheck:
    outcome: ModelLimitOutcome | None
    tenant_id: UUID | None = None
    lease_id: str | None = None
    route_fingerprint: str | None = None
    breaker_state: BreakerState | None = None

    @property
    def half_open_trial(self) -> bool:
        return self.breaker_state is BreakerState.TRIAL


async def prepare_attempt(
    store: ModelLimitStore, tenant_id: UUID, model: ResolvedModel,
) -> ModelLimitCheck:
    """Check the resolved route, then take this tenant's call lease."""
    fingerprint = model.route.fingerprint
    breaker = await store.check_breaker(fingerprint)
    if breaker is BreakerState.OPEN:
        return ModelLimitCheck(ModelLimitOutcome.BREAKER_OPEN, route_fingerprint=fingerprint)
    lease_id = await store.acquire_lease(tenant_id)
    if lease_id is None:
        if breaker is BreakerState.TRIAL:
            await store.release_trial(fingerprint)
        return ModelLimitCheck(ModelLimitOutcome.CONCURRENCY_LIMIT, route_fingerprint=fingerprint)
    return ModelLimitCheck(None, tenant_id, lease_id, fingerprint, breaker)


async def release_attempt(store: ModelLimitStore, check: ModelLimitCheck) -> None:
    if check.tenant_id is not None and check.lease_id is not None:
        await store.release_lease(check.tenant_id, check.lease_id)
