"""Sprint 008, A3: retention and purge of `gateway_decisions` on real Postgres, as the app role.

The purge removes only the expired rows of the right tenant, writes its checkpoint and an outbox event in the same
transaction, and the chain still verifies across the checkpoint. The purge function refuses any other tenant.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from adapters.pg_outbox_events import OutboxEventBus
from core.database import jobs
from core.database.tenant import tenant_connection
from core.identity.admin import admin_connection, set_retention
from evidence import chain
from evidence.receipts import Keyring
from tests.trust_helpers import KEYRING, run_purges, seed_chain, seed_unchained
from workers.handlers.purge import make_purge_handler
from workers.scheduler import schedule_purges

pytestmark = pytest.mark.asyncio

_spec = importlib.util.spec_from_file_location("receipt_script", Path(__file__).resolve().parents[2] / "scripts/verify/receipt.py")
assert _spec and _spec.loader
offline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(offline)


async def rows_of(owner_pool, tenant):
    return await owner_pool.fetch(
        "SELECT chain_position, row_hash FROM gateway_decisions WHERE tenant_id = $1 ORDER BY chain_position NULLS FIRST", UUID(tenant.id))


async def checkpoints_of(owner_pool, tenant):
    return await owner_pool.fetch("SELECT position, row_hash, reason, signature, key_id FROM chain_checkpoints WHERE tenant_id = $1 ORDER BY position", UUID(tenant.id))


async def verified(owner_pool, tenant, dsn):
    export = await asyncio.to_thread(offline.export_from_database, dsn, tenant.id)
    return export, offline.verify_chain(export, KEYRING.public_map())


async def test_the_purge_removes_only_the_expired_rows_of_the_right_tenant(db_pool, owner_pool, tenant_a, tenant_b, database_url):
    a = await seed_chain(owner_pool, tenant_a.id, [200, 150, 100, 95, 10, 5, 1])     # four are older than 90 days
    await seed_chain(owner_pool, tenant_b.id, [300, 120, 2])                           # B has expired rows too
    with admin_connection(database_url) as conn:
        set_retention(conn, "tenant-b", 400)  # ...but B keeps its decisions 400 days
    assert await run_purges(db_pool) == 1  # only A is due
    left = await rows_of(owner_pool, tenant_a)
    assert [r["chain_position"] for r in left] == [5, 6, 7]
    assert len(await rows_of(owner_pool, tenant_b)) == 3  # B untouched
    cp = await checkpoints_of(owner_pool, tenant_a)
    assert [(c["position"], c["reason"]) for c in cp] == [(0, "genesis"), (4, "purge")]
    assert cp[1]["row_hash"] == a[3]["row_hash"]  # the hash of the last deleted row
    export, checks = await verified(owner_pool, tenant_a, database_url)
    assert all(ok for _, ok, _ in checks), checks
    assert export["rows"][0]["position"] == 5 and export["rows"][0]["prev_hash"] == a[3]["row_hash"]


async def test_the_chain_verifies_across_the_checkpoint_and_fails_without_it(db_pool, owner_pool, tenant_a, database_url):
    await seed_chain(owner_pool, tenant_a.id, [120, 100, 3, 2])
    await run_purges(db_pool)
    export, checks = await verified(owner_pool, tenant_a, database_url)
    assert all(ok for _, ok, _ in checks) and [r["position"] for r in export["rows"]] == [3, 4]
    export["checkpoints"] = [c for c in export["checkpoints"] if c["position"] != 2]  # the checkpoint is lost
    assert not all(ok for _, ok, _ in offline.verify_chain(export))
    # the module the server uses agrees
    rows = [chain.ChainRow(r["position"], r["prev_hash"], r["row_hash"], r["decision"]) for r in export["rows"]]
    assert not all(c.ok for c in chain.verify_chain(rows, {0: chain.genesis_hash(tenant_a.id)}))


async def test_a_tenants_own_retention_days_beat_the_platform_default(db_pool, owner_pool, tenant_a, tenant_b, database_url):
    await seed_chain(owner_pool, tenant_a.id, [50, 40, 5])
    await seed_chain(owner_pool, tenant_b.id, [50, 40, 5])
    with admin_connection(database_url) as conn:
        set_retention(conn, "tenant-a", 30)  # A keeps 30 days, B the default 90
    assert await run_purges(db_pool) == 1
    assert [r["chain_position"] for r in await rows_of(owner_pool, tenant_a)] == [3]
    assert [r["chain_position"] for r in await rows_of(owner_pool, tenant_b)] == [1, 2, 3]
    with admin_connection(database_url) as conn:
        set_retention(conn, "tenant-a", None)  # back to the default
    assert await owner_pool.fetchval("SELECT retention_days FROM tenants WHERE slug = 'tenant-a'") is None


async def test_unchained_rows_expire_by_age_too(db_pool, owner_pool, tenant_a):
    old = await seed_unchained(owner_pool, tenant_a.id, [200, 100, 1])
    await seed_chain(owner_pool, tenant_a.id, [120, 1])
    await run_purges(db_pool)
    ids = {r["id"] for r in await owner_pool.fetch("SELECT id FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id))}
    assert old[2] in ids and old[0] not in ids and old[1] not in ids
    assert await owner_pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id)) == 2


async def test_batches_write_a_checkpoint_each_and_the_chain_still_verifies(db_pool, owner_pool, tenant_a, database_url):
    await seed_chain(owner_pool, tenant_a.id, [300, 280, 260, 240, 220, 200, 3, 2])  # six expired
    await run_purges(db_pool, batch=2)
    cp = await checkpoints_of(owner_pool, tenant_a)
    assert [(c["position"], c["reason"]) for c in cp] == [(0, "genesis"), (2, "purge"), (4, "purge"), (6, "purge")]
    _, checks = await verified(owner_pool, tenant_a, database_url)
    assert all(ok for _, ok, _ in checks) and len(await rows_of(owner_pool, tenant_a)) == 2


async def test_everything_expired_still_lets_the_chain_continue(db_pool, owner_pool, tenant_a, database_url):
    """A tenant that was quiet for a long time loses every row; its next decision links to the checkpoint."""
    await seed_chain(owner_pool, tenant_a.id, [300, 200])
    await run_purges(db_pool)
    assert await rows_of(owner_pool, tenant_a) == []
    from adapters.pg_evidence import PgDecisionSink
    from ports import DecisionEntry

    await PgDecisionSink(db_pool).write(DecisionEntry(
        tenant_id=UUID(tenant_a.id), principal_id=UUID(tenant_a.principal_id), request_id="after-purge",
        trace_id="after-purge", action="kb.read", resource="legal", outcome="allow", stage="allow",
        reason="allowed", policy_version=None, input_sha256=None, execution_id=None, extensions={},
    ))
    export, checks = await verified(owner_pool, tenant_a, database_url)
    assert [r["position"] for r in export["rows"]] == [3]
    assert all(ok for _, ok, _ in checks), checks


async def test_the_purge_writes_its_checkpoint_and_an_outbox_event_in_one_transaction(db_pool, owner_pool, tenant_a):
    await seed_chain(owner_pool, tenant_a.id, [200, 100, 4])
    await run_purges(db_pool, events=OutboxEventBus(db_pool), batch=1)
    events = await owner_pool.fetch("SELECT event FROM outbox WHERE tenant_id = $1 ORDER BY created_at", UUID(tenant_a.id))
    bodies = [json.loads(e["event"]) if isinstance(e["event"], str) else e["event"] for e in events]
    assert [b["type"] for b in bodies] == ["platform.gateway.purge.v1"] * 2
    assert [b["data"]["checkpoint_position"] for b in bodies] == [1, 2] and all(b["data"]["purged"] == 1 for b in bodies)
    assert all(set(b["data"]) == {"job_id", "purged", "retention_days", "checkpoint_position", "checkpoint_hash"} for b in bodies)


async def test_a_failed_event_write_rolls_the_checkpoint_and_the_delete_back(db_pool, owner_pool, tenant_a):
    class Broken:
        async def publish(self, event, *, tx=None):
            raise RuntimeError("outbox down")

        def subscribe(self, *a, **k):
            return None

    await seed_chain(owner_pool, tenant_a.id, [200, 100, 4])
    created = await schedule_purges(db_pool, 90)
    assert created == 1
    handler = make_purge_handler(Broken(), 90, 10, KEYRING.sign)
    job = None
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        job = (await jobs.list_jobs(conn, kind=jobs.KIND_PURGE))[0]

    class Ctx:
        pool = db_pool

    with pytest.raises(RuntimeError):
        await handler(job, Ctx())  # type: ignore[arg-type]
    assert len(await rows_of(owner_pool, tenant_a)) == 3  # nothing deleted
    assert [c["reason"] for c in await checkpoints_of(owner_pool, tenant_a)] == ["genesis"]  # and no checkpoint


async def test_the_purge_function_refuses_another_tenant_and_a_missing_one(db_pool, owner_pool, tenant_a, tenant_b):
    await seed_chain(owner_pool, tenant_b.id, [200, 100])
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        with pytest.raises(asyncpg.PostgresError, match="not the caller's tenant"):
            await conn.fetch("SELECT * FROM decisions_purge_batch($1, 90, 10, NULL, NULL, NULL, NULL)", UUID(tenant_b.id))
    async with db_pool.acquire() as conn:  # no tenant set at all
        with pytest.raises(asyncpg.PostgresError, match="not the caller's tenant"):
            await conn.fetch("SELECT * FROM decisions_purge_batch($1, 90, 10, NULL, NULL, NULL, NULL)", UUID(tenant_b.id))
    assert len(await rows_of(owner_pool, tenant_b)) == 2


async def test_the_app_role_has_no_delete_or_update_on_decisions_and_cannot_set_retention(db_pool, owner_pool, tenant_a):
    await seed_chain(owner_pool, tenant_a.id, [200])
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        for sql in ("DELETE FROM gateway_decisions", "UPDATE gateway_decisions SET reason = 'x'",
                    "UPDATE tenants SET retention_days = 1", "DELETE FROM chain_checkpoints"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with conn.transaction():
                    await conn.execute(sql)
    assert len(await rows_of(owner_pool, tenant_a)) == 1


async def test_the_purge_function_is_executable_by_the_app_role_only(owner_pool):
    for sig in ("decisions_purge_plan(uuid, integer, integer)", "decisions_purge_batch(uuid, integer, integer, bigint, text, text, text)", "retention_due_tenants(integer)", "trust_jobs_by_status()", "trust_outbox_lag()"):
        row = await owner_pool.fetchrow("SELECT prosecdef, proconfig FROM pg_proc WHERE oid = $1::regprocedure", sig)
        assert row["prosecdef"] is True and any(c.startswith("search_path=") for c in row["proconfig"]), sig
        assert await owner_pool.fetchval("SELECT has_function_privilege('gap_app', $1, 'EXECUTE')", sig) is True
        assert await owner_pool.fetchval("SELECT has_function_privilege('public', $1, 'EXECUTE')", sig) is False


async def test_the_scheduler_queues_one_job_a_day_for_a_tenant_with_expired_rows_only(db_pool, owner_pool, tenant_a, tenant_b):
    await seed_chain(owner_pool, tenant_a.id, [200, 1])
    await seed_chain(owner_pool, tenant_b.id, [5, 1])  # nothing expired
    assert await schedule_purges(db_pool, 90) == 1
    assert await schedule_purges(db_pool, 90) == 0 and await schedule_purges(db_pool, 90) == 0  # same day: idempotent
    rows = await owner_pool.fetch("SELECT tenant_id, kind, status FROM jobs")
    assert [(str(r["tenant_id"]), r["kind"], r["status"]) for r in rows] == [(tenant_a.id, "purge_decisions", "queued")]


async def test_a_second_purge_with_nothing_expired_changes_nothing(db_pool, owner_pool, tenant_a):
    await seed_chain(owner_pool, tenant_a.id, [200, 3])
    await run_purges(db_pool)
    before = (await rows_of(owner_pool, tenant_a), await checkpoints_of(owner_pool, tenant_a))
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        row = await conn.fetchrow("SELECT * FROM decisions_purge_batch($1, 90, 10, NULL, NULL, NULL, NULL)", UUID(tenant_a.id))
    assert row["purged"] == 0 and row["checkpoint_position"] is None
    assert (await rows_of(owner_pool, tenant_a), await checkpoints_of(owner_pool, tenant_a)) == before


# ------------------------------------------------------------------ QA fixes (Sprint 008)

async def test_m2_the_purge_never_goes_below_30_days_whatever_the_caller_passes(db_pool, owner_pool, tenant_a):
    """Without the floor a caller could pass 1 day and purge its own tenant down to yesterday."""
    await seed_chain(owner_pool, tenant_a.id, [200, 60, 20, 5])
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        plan = await conn.fetchrow("SELECT * FROM decisions_purge_plan($1, 1, 100)", UUID(tenant_a.id))
    assert (plan["plan_days"], plan["plan_position"]) == (30, 2)  # positions 1 and 2 (200 and 60 days) only
    assert await run_purges(db_pool, default_days=1) in (0, 1)
    assert [r["chain_position"] for r in await rows_of(owner_pool, tenant_a)] == [3, 4]  # the 20 and 5 day rows stay
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        zero = await conn.fetchrow("SELECT * FROM decisions_purge_plan($1, 0, 100)", UUID(tenant_a.id))
    assert zero["plan_days"] == 30
    with pytest.raises(asyncpg.CheckViolationError):  # a stored retention below 30 is refused too
        await owner_pool.execute("UPDATE tenants SET retention_days = 7 WHERE slug = 'tenant-a'")


async def test_m1_the_app_role_cannot_write_a_checkpoint(db_pool, owner_pool, tenant_a):
    await seed_chain(owner_pool, tenant_a.id, [200, 100, 2])
    async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "INSERT INTO chain_checkpoints (tenant_id, position, row_hash, reason, signature, key_id) "
                "VALUES ($1, 2, repeat('a', 64), 'purge', 'x', 'y')", UUID(tenant_a.id))


async def test_m1_the_purge_function_refuses_a_checkpoint_that_is_not_what_it_computes_or_is_unsigned(db_pool, owner_pool, tenant_a):
    rows = await seed_chain(owner_pool, tenant_a.id, [200, 100, 2])
    good = (2, rows[1]["row_hash"])
    cases = [
        ((2, "f" * 64, "sig", "kid"), "not the one the database computes"),   # a forged hash
        ((3, rows[2]["row_hash"], "sig", "kid"), "not the one the database computes"),  # a forged, later position
        ((*good, None, "kid"), "needs a signature"),
        ((*good, "", "kid"), "needs a signature"),
        ((*good, "sig", None), "needs a signature"),
    ]
    for args, message in cases:
        async with tenant_connection(db_pool, UUID(tenant_a.id)) as conn:
            with pytest.raises(asyncpg.PostgresError, match=message):
                await conn.fetch("SELECT * FROM decisions_purge_batch($1, 90, 10, $2, $3, $4, $5)", UUID(tenant_a.id), *args)
    assert len(await rows_of(owner_pool, tenant_a)) == 3  # nothing was deleted by a refused call


async def test_m1_a_purge_checkpoint_is_signed_and_verification_rejects_an_unsigned_or_badly_signed_one(db_pool, owner_pool, tenant_a, database_url):
    await seed_chain(owner_pool, tenant_a.id, [200, 100, 2])
    await run_purges(db_pool)
    export, checks = await verified(owner_pool, tenant_a, database_url)
    assert all(ok for _, ok, _ in checks), checks
    [purge] = [c for c in export["checkpoints"] if c["reason"] == "purge"]
    assert purge["key_id"] == KEYRING.active_key_id and purge["signature"]
    # the server-side check agrees
    from evidence.receipts import verify_checkpoints

    assert verify_checkpoints(tenant_a.id, export["checkpoints"], KEYRING.public_map()).ok
    # unsigned, a changed hash (the signature no longer fits), another key, and no key given at all
    for change in (lambda c: c.update(signature=None), lambda c: c.update(row_hash="e" * 64),
                   lambda c: c.update(signature=purge["signature"][:-4] + "AAAA")):
        bad = json.loads(json.dumps(export))
        change(next(c for c in bad["checkpoints"] if c["reason"] == "purge"))
        assert not all(ok for _, ok, _ in offline.verify_chain(bad, KEYRING.public_map()))
        assert not verify_checkpoints(tenant_a.id, bad["checkpoints"], KEYRING.public_map()).ok
    other = Keyring.generate().public_map()
    assert not all(ok for _, ok, _ in offline.verify_chain(export, other))
    assert not all(ok for _, ok, _ in offline.verify_chain(export))  # keys are required once a purge checkpoint exists
