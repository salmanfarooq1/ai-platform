"""WP3 live: the shared purge lock, the online dump-derived manifest and the refusal of incomplete object sets."""
import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from uuid import UUID

import pytest

from core.database import locks
from scripts.poc_lib import lifecycle
from scripts.poc_lib.runner import LocalRunner
from scripts.poc_lib.up import PocError
from tests.integration.poc.conftest import ROOT
from tests.trust_helpers import run_purges, seed_chain

_BOUNDARY = "pocboundary"
_HEADERS = {"Content-Type": f"multipart/form-data; boundary={_BOUNDARY}"}


def _body(text):
    return (f"--{_BOUNDARY}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"note.md\"\r\n"
            f"Content-Type: text/markdown\r\n\r\n{text}\r\n--{_BOUNDARY}--\r\n").encode()


EXPECTED_TABLES = {"tenants", "principals", "api_keys", "policies", "knowledge_bases", "documents", "jobs", "outbox",
                   "processed_events", "gateway_decisions", "chain_heads", "chain_checkpoints"}


# --- the lock, on the real Postgres the integration tier uses ----------------------------------------------------------

@pytest.mark.asyncio
async def test_purge_waits_during_backup(db_pool, owner_pool, tenant_a):
    await seed_chain(owner_pool, tenant_a.id, [200, 150, 100, 95, 10, 5, 1])
    tenant = UUID(tenant_a.id)

    async def remaining():
        return await owner_pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1", tenant)

    assert await remaining() == 7
    # 1. While capture owns the lock, the purge job waits before it plans, signs or deletes.
    async with owner_pool.acquire() as backup_conn:
        async with locks.backup_guard(backup_conn, timeout=5):
            purge = asyncio.create_task(run_purges(db_pool, timeout=25))
            await asyncio.sleep(1.5)
            assert not purge.done()
            assert await remaining() == 7
        assert await asyncio.wait_for(purge, 30) == 1  # the lock was released: the purge resumes and finishes
    assert await remaining() == 3

    # 2. An in-flight purge transaction delays capture: the backup waits, and times out rather than hanging.
    async with owner_pool.acquire() as purge_conn, owner_pool.acquire() as backup_conn:
        async with purge_conn.transaction():
            await locks.purge_guard(purge_conn)
            started = time.monotonic()
            with pytest.raises(locks.BackupLockTimeout):
                async with locks.backup_guard(backup_conn, timeout=0.5):
                    pytest.fail("capture must not start while a purge holds the lock")
            assert 0.4 <= time.monotonic() - started < 5
        async with locks.backup_guard(backup_conn, timeout=5):  # the purge ended: capture proceeds
            pass

    # 3. Errors and cancellation release the lock; a later purge is not blocked.
    async def lock_is_free() -> bool:
        async with owner_pool.acquire() as probe:
            got = await probe.fetchval("SELECT pg_try_advisory_lock($1)", locks.BACKUP_LOCK_KEY)
            if got:
                await probe.execute("SELECT pg_advisory_unlock($1)", locks.BACKUP_LOCK_KEY)
            return bool(got)

    async with owner_pool.acquire() as conn:
        with pytest.raises(RuntimeError, match="capture failed"):
            async with locks.backup_guard(conn, timeout=5):
                raise RuntimeError("capture failed")
    assert await lock_is_free()

    async def hold_forever():
        async with owner_pool.acquire() as conn:
            async with locks.backup_guard(conn, timeout=5):
                await asyncio.sleep(60)

    holder = asyncio.create_task(hold_forever())
    await asyncio.sleep(0.5)
    assert not await lock_is_free()
    holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await holder
    assert await lock_is_free()


# --- a real stack ----------------------------------------------------------------------------------------------------

# --- fix round 1: the real psql-session lock (pg.take_backup_lock), not locks.backup_guard --------------------------------

_ENQUEUE_PURGES = (
    "import asyncio, uuid\n"
    "from core.database import jobs\n"
    "from core.database.pool import create_pool\n"
    "from core.database.tenant import tenant_connection\n"
    "from core.settings import get_settings\n"
    "async def main():\n"
    "    pool = await create_pool()\n"
    "    rows = await pool.fetch('SELECT due_tenant FROM retention_due_tenants($1)', get_settings().decision_retention_days)\n"
    "    for row in rows:  # the scheduler's own query; a unique key, because the day's scheduled job may already be done\n"
    "        async with tenant_connection(pool, row['due_tenant']) as conn:\n"
    "            await jobs.enqueue(conn, row['due_tenant'], jobs.KIND_PURGE, {}, idempotency_key='fix1-' + uuid.uuid4().hex, max_attempts=3)\n"
    "    print('QUEUED', len(rows))\n"
    "asyncio.run(main())\n"
)


def _old_decisions(live) -> int:
    return int(live.psql("SELECT count(*) FROM gateway_decisions WHERE created_at < now() - interval '90 days'"))


def _purge_status(live) -> list[str]:
    return live.psql("SELECT status FROM jobs WHERE kind = 'purge_decisions' ORDER BY created_at").split()


def test_purge_waits_while_the_real_backup_lock_session_is_held(poc_stack):
    """The stack's own worker runs the real purge handler against the real psql-session lock.

    This must be the first test that writes decisions on the module's stack: a purge deletes a prefix of the chain, so
    old rows seeded after newer ones could never be purged and the test would prove nothing."""
    from scripts.poc_backup import pg

    live = poc_stack
    live.seed_decisions(ages_days=[210, 180, 150, 0.001])  # one recent row last: the purge keeps the chain head
    assert _old_decisions(live) >= 3
    context = live.context()
    session = pg.take_backup_lock(context)
    try:
        queued = context.compose("run", "--rm", "--no-deps", "-T", "api", "python", "-", input=_ENQUEUE_PURGES.encode()).text
        assert "QUEUED 1" in queued
        before = _old_decisions(live)
        time.sleep(10)  # the worker has long since claimed the job; it must be waiting on the lock
        assert _old_decisions(live) == before, "a purge deleted rows while the backup lock session was held"
        assert "succeeded" not in _purge_status(live)[-1:]
    finally:
        session.close()
    deadline = time.monotonic() + 90
    while _old_decisions(live) != 0:  # the lock is gone: the same purge resumes and completes
        assert time.monotonic() < deadline, f"the purge never finished after the lock was released: {_purge_status(live)}"
        time.sleep(1)
    assert _purge_status(live)[-1] == "succeeded"


# --- fix round 1 (continued): a killed lock session fails the backup (below) ----------------------------------------------


def _no_advisory_lock_held(live) -> bool:
    for _ in range(10):  # the database session of a closed `psql` ends a moment after its client
        if live.psql("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'").strip() == "0":
            return True
        time.sleep(0.5)
    return False


def test_online_manifest_matches_dump_snapshot(poc_stack):
    live = poc_stack
    key = live.api_key()
    live.seed_decisions(3)
    first = live.ingest(key, "  \n")
    assert live.wait_job(key, first["job_id"])["status"] == "succeeded"
    accepted, stop = [], threading.Event()

    def writer():  # ordinary traffic keeps flowing while capture runs
        n = 3
        while not stop.is_set():
            n += 1
            try:
                accepted.append(live.call("POST", "/v1/ingest?namespace=default", key, data=_body(" " * n + "\n"),
                                          headers=_HEADERS)["job_id"])
            except Exception:  # noqa: BLE001 - counted below: every accepted call must be recorded, a refused one is not a loss
                pass
            time.sleep(1.0)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        ref = lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))
    finally:
        stop.set()
        thread.join(30)
    context = live.context()
    manifest = lifecycle.load_manifest(context, ref)
    assert accepted, "the concurrent writer never got a call through"
    recorded = {line for line in live.psql("SELECT id FROM jobs").split()}
    assert set(accepted) <= recorded  # every accepted write stayed recorded
    assert manifest["version"] == 1 and manifest["stack"] == live.name
    assert EXPECTED_TABLES <= set(manifest["counts"])
    assert manifest["counts"]["jobs"] >= 1 and manifest["counts"]["chain_checkpoints"] >= 1
    assert manifest["schema_head"] == live.psql("SELECT version_num FROM alembic_version").strip()
    heads = {row[0]: row[1:] for row in manifest["heads"]}
    assert heads[live.tenant()][0] >= 3
    secrets = lifecycle.stack_secrets(context)
    assert manifest["signing"] == secrets.public_identity()
    private = secrets.key_file.read_text().strip()
    assert private not in json.dumps(manifest)
    assert manifest["release_manifest_sha256"] == hashlib.sha256((live.folder / "release-manifest.json").read_bytes()).hexdigest()
    assert manifest["dump"]["sha256"] and manifest["cost_counters"]["date"]
    objects = {o["key"]: o for o in manifest["objects"]}
    assert first["job_id"] and objects, "an ingested object must be in the snapshot"
    assert all(k == o["sha256"] for k, o in objects.items())  # content addressed
    referenced = set(live.psql("SELECT DISTINCT payload->>'object_key' FROM jobs WHERE payload ? 'object_key'").split())
    assert set(objects) <= referenced
    # The scratch restore of the stored dump reproduces the manifest exactly, whatever was written afterwards.
    live.ingest(key, " " * 400 + "\n")
    after = live.psql("SELECT count(*) FROM jobs")
    assert int(after) > manifest["counts"]["jobs"]  # post-snapshot rows are not in the snapshot
    lifecycle.RealBackend(context).verify(ref)
    assert _no_advisory_lock_held(live)
    assert not (live.folder / "staging").exists() or not any((live.folder / "staging").iterdir())


def test_missing_or_corrupt_object_refuses_backup(poc_stack):
    live = poc_stack
    tenant = live.tenant()
    good = lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))
    pointer = (live.folder / "latest.json").read_text()
    wrong_bytes = b"this is not the content that hashes to the key"
    key_hash = hashlib.sha256(b"the expected content").hexdigest()

    def refuse(payload_key: str, message: str):
        live.psql("DELETE FROM jobs WHERE idempotency_key = 'poc-bad-object'")
        live.psql(f"INSERT INTO jobs (tenant_id, kind, status, payload, idempotency_key) VALUES ('{tenant}', 'ingest', "
                  f"'succeeded', jsonb_build_object('object_key', '{payload_key}'), 'poc-bad-object')")
        with pytest.raises(PocError, match=message):
            lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))
        assert (live.folder / "latest.json").read_text() == pointer  # latest did not move
        assert _no_advisory_lock_held(live)  # the lock was released
        assert not (live.folder / "staging").exists() or not any((live.folder / "staging").iterdir())

    try:
        refuse("ab" * 32, "missing")
        live.compose("exec", "-T", "api", "sh", "-c",
                     f"mkdir -p /data/objects/{key_hash[:2]} && cat > /data/objects/{key_hash[:2]}/{key_hash}", input=wrong_bytes)
        refuse(key_hash, "corrupt")
        for unsafe in ("../../etc/passwd", "AB" * 32, "ab/../" + "c" * 58, "x"):
            refuse(unsafe, "unsafe")
    finally:
        live.psql("DELETE FROM jobs WHERE idempotency_key = 'poc-bad-object'")
        live.compose("exec", "-T", "api", "sh", "-c", f"rm -f /data/objects/{key_hash[:2]}/{key_hash}", check=False)
    again = lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))
    assert again.snapshot_id != good.snapshot_id  # a clean set backs up again
    assert Path(live.folder / "latest.json").read_text() != pointer


class KillLockSessionRunner(LocalRunner):
    """Runs everything for real, but ends the lock's database session just before the dump (a test-only fault seam)."""

    def __init__(self, live):
        self.live, self.killed = live, 0

    def run(self, argv, **kwargs):
        if "pg_dump" in argv and not self.killed:
            self.killed = int(self.live.psql(
                "SELECT count(pg_terminate_backend(pid)) FROM pg_locks "
                f"WHERE locktype = 'advisory' AND granted AND objid = {locks.BACKUP_LOCK_KEY & 0xFFFFFFFF}").strip())
        return super().run(argv, **kwargs)


def test_killing_the_lock_session_makes_the_backup_fail(poc_stack):
    from scripts.poc_backup.restic import Restic

    live = poc_stack
    good = lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))
    pointer = (live.folder / "latest.json").read_text()
    snapshots = [row["id"] for row in Restic(live.context()).snapshots()]
    runner = KillLockSessionRunner(live)
    with pytest.raises(PocError, match="lock"):
        lifecycle.backup(ROOT, live.name, runner=runner, environ=dict(os.environ))
    assert runner.killed == 1, "the fault seam did not find the lock session"
    assert (live.folder / "latest.json").read_text() == pointer  # no snapshot pointer was written
    assert [row["id"] for row in Restic(live.context()).snapshots()] == snapshots  # and no snapshot was stored
    assert _no_advisory_lock_held(live)
    assert not (live.folder / "staging").exists() or not any((live.folder / "staging").iterdir())
    again = lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))  # the next backup is fine
    assert again.snapshot_id != good.snapshot_id
