"""Helpers for the retention tests: write a valid decision chain with chosen timestamps, and run purge jobs.

`seed_chain` writes rows as the owner role with the same hashing the gateway uses (`gateway.chain`), so a test can age
rows without breaking their chain. `run_purges` queues the purge jobs the scheduler would and runs a worker until they
are done, all as the app role.
"""
import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from core.database import jobs
from gateway import chain
from gateway.receipts import Keyring
from ports import EventBus
from workers.handlers.purge import make_purge_handler
from workers.loop import Worker
from workers.scheduler import schedule_purges

# The key that signs the checkpoints of the purges these helpers run. Tests that check the signature read its public key.
KEYRING = Keyring.generate()


def days_ago(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def seed_chain(
    owner_pool: Any, tenant_id: str, ages_in_days: Sequence[float], *, outcome: str = "allow", request_id: str = "seed",
) -> list[dict[str, Any]]:
    """Append one chained decision per age (oldest first, so the ages must not increase). Returns the rows written."""
    tenant = UUID(tenant_id)
    genesis = chain.genesis_hash(tenant)
    await owner_pool.execute("INSERT INTO chain_heads (tenant_id, position, row_hash) VALUES ($1, 0, $2) ON CONFLICT DO NOTHING", tenant, genesis)
    await owner_pool.execute(
        "INSERT INTO chain_checkpoints (tenant_id, position, row_hash, reason) VALUES ($1, 0, $2, 'genesis') ON CONFLICT DO NOTHING",
        tenant, genesis,
    )
    head = await owner_pool.fetchrow("SELECT position, row_hash FROM chain_heads WHERE tenant_id = $1", tenant)
    position, prev = int(head["position"]), str(head["row_hash"])
    written = []
    for age in ages_in_days:
        position += 1
        decision_id, created = uuid4(), days_ago(age).replace(microsecond=123456)
        record = chain.decision_record(
            id=decision_id, tenant_id=tenant, principal_id=None, request_id=request_id, action="kb.read", resource="legal",
            outcome=outcome, stage="allow", reason="allowed", policy_version=None, input_sha256=None, execution_id=None,
            created_at=created,
        )
        row_hash = chain.compute_row_hash(record, prev)
        await owner_pool.execute(
            "INSERT INTO gateway_decisions (id, tenant_id, request_id, trace_id, action, resource, outcome, stage, reason, "
            "created_at, chain_position, prev_hash, row_hash) VALUES ($1, $2, $3, $4, 'kb.read', 'legal', $5, 'allow', 'allowed', "
            "$6, $7, $8, $9)",
            decision_id, tenant, request_id, "t" * 32, outcome, created, position, prev, row_hash,
        )
        written.append({"id": decision_id, "position": position, "row_hash": row_hash, "prev_hash": prev})
        prev = row_hash
    await owner_pool.execute("UPDATE chain_heads SET position = $2, row_hash = $3 WHERE tenant_id = $1", tenant, position, prev)
    return written


async def seed_unchained(owner_pool: Any, tenant_id: str, ages_in_days: Sequence[float]) -> list[UUID]:
    """Rows with no chain link: written before migration 0009, or a deny whose chain step failed."""
    ids = []
    for age in ages_in_days:
        ids.append(await owner_pool.fetchval(
            "INSERT INTO gateway_decisions (tenant_id, request_id, trace_id, action, resource, outcome, stage, reason, created_at) "
            "VALUES ($1, 'old', $2, 'kb.read', 'legal', 'allow', 'allow', 'allowed', $3) RETURNING id",
            UUID(tenant_id), "t" * 32, days_ago(age),
        ))
    return ids


async def run_purges(
    app_pool: Any, *, events: EventBus | None = None, default_days: int = 90, batch: int = 1000, timeout: float = 20.0,
    keyring: Keyring | None = None,
) -> int:
    """Queue today's purge jobs (the scheduler's own function) and run a worker until each one has finished. Returns how
    many jobs were queued."""
    created = await schedule_purges(app_pool, default_days)
    worker = Worker(
        app_pool, {jobs.KIND_PURGE: make_purge_handler(events, default_days, batch, (keyring or KEYRING).sign)}, name="purge-test", lease_seconds=30,
        poll_interval=0.02, beat_interval=0.1, backoff_base=0.0, shutdown_grace=0.3, events=events,
    )
    task = asyncio.create_task(worker.run(1))
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        while worker.completed < created:
            if asyncio.get_running_loop().time() > deadline:
                raise AssertionError("purge jobs did not finish in time")
            await asyncio.sleep(0.03)
    finally:
        worker.stop()
        await asyncio.wait_for(task, 10)
    return created
