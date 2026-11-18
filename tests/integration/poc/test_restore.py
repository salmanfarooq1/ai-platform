"""WP2 recovery identity: no trust in ids without the exact public bytes."""
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.settings import Settings
from evidence.receipts import keyring_from_settings


def test_wrong_key_id_requires_previous_public_key(tmp_path):
    from scripts.poc_backup.keys import validate_restore_key
    from scripts.poc_lib.keys import ensure_stack_secrets

    old = ensure_stack_secrets(tmp_path, "old-key")
    new = ensure_stack_secrets(tmp_path, "new-key")
    public = old.public_identity()
    active = Settings(receipt_signing_key_file=str(new.key_file))
    with pytest.raises(ValueError):
        validate_restore_key(public, active)
    rotated = Settings(receipt_signing_key_file=str(new.key_file), receipt_previous_public_keys=public["public_key"])
    validate_restore_key(public, rotated)
    validate_restore_key(new.public_identity(), active)
    for bad in (
        {**public, "key_id": new.public_identity()["key_id"]},
        {**public, "key_id": "fabricated"},
        {**public, "public_key": new.public_identity()["public_key"]},
        {**public, "public_key": "malformed!"},
        {},
    ):
        with pytest.raises(ValueError):
            validate_restore_key(bad, rotated)
    with pytest.raises(ValueError):
        validate_restore_key(public, Settings(receipt_previous_public_keys=public["public_key"]))
    old_ring = keyring_from_settings(Settings(receipt_signing_key_file=str(old.key_file)))
    signature, kid = old_ring.sign("saved receipt canonical text")
    new_ring = keyring_from_settings(rotated)
    Ed25519PublicKey.from_public_bytes(new_ring.public_raw(kid)).verify(
        base64.b64decode(signature), b"saved receipt canonical text",
    )
    assert new_ring.sign("new receipt")[1] == new.public_identity()["key_id"]
    new.key_file.unlink()
    # Even an already-loaded Settings cannot stand in for the operator's missing recovery file.
    with pytest.raises(ValueError):
        validate_restore_key(public, rotated)


# --- WP3 live: tampering, the restic gate and the full checked down / restoring up journey ------------------------------

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from uuid import UUID  # noqa: E402

import config  # noqa: E402
from gateway import limits  # noqa: E402
from scripts.poc_backup import restic as restic_module  # noqa: E402
from scripts.poc_backup import restore as restore_module  # noqa: E402
from scripts.poc_backup import verify as verify_module  # noqa: E402
from scripts.poc_lib import lifecycle  # noqa: E402
from scripts.poc_lib.runner import CommandError, LocalRunner  # noqa: E402
from scripts.poc_lib.up import PocError, up  # noqa: E402
from tests.integration.poc.conftest import ROOT  # noqa: E402


def _backup(live):
    return lifecycle.backup(ROOT, live.name, runner=LocalRunner(), environ=dict(os.environ))


def _volumes_exist(live) -> dict:
    return {name: subprocess.run(["docker", "volume", "inspect", name], capture_output=True).returncode == 0
            for name in live.marker["volumes"]}


def _healthy(live) -> bool:
    rows = live.services()
    return {"postgres", "valkey", "api", "worker"} == set(rows) and all(
        r["State"] == "running" and r["Health"] == "healthy" for r in rows.values())


def test_manifest_tampering_blocks_health(poc_stack, tmp_path):
    live = poc_stack
    key = live.api_key()
    live.seed_decisions(2)
    assert live.wait_job(key, live.ingest(key, "   \n")["job_id"])["status"] == "succeeded"
    ref = _backup(live)
    context = live.context()
    restored = restic_module.Restic(context).restore(ref)
    manifest = lifecycle.load_manifest(context, ref)
    assert verify_module.verify_restore_set(context, restored, manifest).comparable() == lifecycle.state_of(manifest).comparable()

    def edit_manifest(path, value_of):
        def apply(directory, data):
            data = json.loads(json.dumps(data))
            target = data
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value_of(target[path[-1]])
            return data
        return apply

    def damage_dump(directory, data):
        with open(directory / "dump.pgc", "ab") as stream:
            stream.write(b"x")
        return data

    def damage_object(directory, data):
        victim = next((directory / "objects").iterdir())
        victim.write_bytes(victim.read_bytes() + b"tampered")
        return data

    cases = {
        "schema": edit_manifest(["schema_head"], lambda _: "0001"),
        "dump bytes": damage_dump,
        "object bytes": damage_object,
        "row count": edit_manifest(["counts", "jobs"], lambda n: n + 1),
        "tenant head": edit_manifest(["heads", 0, 1], lambda n: n + 1),
        "checkpoint": edit_manifest(["checkpoints", 0, 2], lambda _: "0" * 64),
        "key id": edit_manifest(["signing", "key_id"], lambda _: "forged-key-id"),
        "public key": edit_manifest(["signing", "public_key"], lambda _: "AAAA" * 11),
        "release digest": edit_manifest(["release_manifest_sha256"], lambda _: "0" * 64),
    }
    before = live.psql("SELECT count(*) FROM jobs")
    for label, change in cases.items():
        copy = tmp_path / label.replace(" ", "-")
        shutil.copytree(restored, copy)
        tampered = change(copy, manifest)
        with pytest.raises(PocError):
            verify_module.verify_restore_set(context, copy, tampered)
        assert live.psql("SELECT count(*) FROM pg_database WHERE datname LIKE 'poc_scratch_%'").strip() == "0", label
    assert live.services()["api"]["State"] == "running"  # nothing was started or stopped by a failed verification
    # A restore never overwrites a populated target.
    with pytest.raises(PocError, match="not empty"):
        restore_module.load_into_empty_database(context, restored, manifest)
    assert live.psql("SELECT count(*) FROM jobs") == before


def _flip_a_byte(path):
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.chmod(0o600)  # restic stores packs read-only
    path.write_bytes(bytes(data))


def test_restic_check_and_scratch_restore_gate_down(poc_stack):
    live = poc_stack
    live.seed_decisions(1)
    ref = _backup(live)
    context = live.context()
    backend = lifecycle.RealBackend(context)
    backend.verify(ref)  # the intact set: a real read-data check and a real scratch restore both pass
    environ = {**os.environ, "POC_RECOVERY_REF": ref.snapshot_id}
    jobs_before = live.psql("SELECT count(*) FROM jobs")
    secrets_before = (live.folder / "receipt-signing.key").read_bytes()

    def assert_nothing_removed():
        assert all(_volumes_exist(live).values())
        assert _healthy(live), "the refusal must start the services again"
        assert live.psql("SELECT count(*) FROM jobs") == jobs_before
        assert (live.folder / "receipt-signing.key").read_bytes() == secrets_before
        assert (live.folder / "marker.json").exists() and (live.folder / "restic-password").exists()

    # Damaged restic data: the read-data check fails and down refuses.
    pack = max((p for p in (live.folder / "backups" / "data").rglob("*") if p.is_file()), key=lambda p: p.stat().st_size)
    original = pack.read_bytes()
    _flip_a_byte(pack)
    try:
        with pytest.raises(PocError, match="restic check"):
            backend.verify(ref)
        with pytest.raises(PocError):
            lifecycle.down(ROOT, live.name, runner=LocalRunner(), environ=environ, backend=lifecycle.RealBackend(context))
        assert_nothing_removed()
    finally:
        pack.write_bytes(original)
        pack.chmod(0o400)

    # An injected scratch-restore failure refuses as well.
    def fail_restore():
        raise PocError("injected scratch restore failure")

    broken = lifecycle.RealBackend(context, before_scratch_restore=fail_restore)
    with pytest.raises(PocError, match="injected"):
        lifecycle.down(ROOT, live.name, runner=LocalRunner(), environ=environ, backend=broken)
    assert_nothing_removed()
    backend.verify(ref)  # and the repository is healthy again


# --- fix round 1: the manifest digest binds the pointer, the repository and the restore, on real restic snapshots -------

def _store_snapshot(live, manifest_bytes: bytes, claimed_digest: str) -> str:
    """Store a snapshot holding only `manifest.json` through the real restic service. `claimed_digest` is the value of
    the snapshot's `manifest-<digest>` tag (an attacker keeps it equal to the genuine one)."""
    staging = restic_module.private_dir(live.folder / "staging", fresh=True)
    (staging / "manifest.json").write_bytes(manifest_bytes)
    try:
        return restic_module.Restic(live.context()).backup(claimed_digest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _publish(live, snapshot_id: str, digest: str, stored: dict) -> lifecycle.BackupRef:
    ref = lifecycle.BackupRef(live.name, snapshot_id, digest, datetime.now(timezone.utc), lifecycle.state_of(stored))
    lifecycle.catalog.write_pointer(live.folder, ref)
    return ref


def test_manifest_digest_binding_is_enforced_on_real_snapshots(poc_stack):
    live = poc_stack
    live.seed_decisions(1)
    genuine = _backup(live)
    context = live.context()
    manifest = lifecycle.load_manifest(context, genuine)
    good_pointer = (live.folder / "latest.json").read_text()
    genuine_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    assert hashlib.sha256(genuine_raw).hexdigest() == genuine.manifest_sha256  # the stored bytes, reproduced exactly
    now = lambda: datetime.now(timezone.utc)  # noqa: E731

    def refused(label, *patterns):
        """latest_ref, restore_latest and verify_snapshot all refuse the published state."""
        for call in (lambda: lifecycle.catalog.latest_ref(live.context()),
                     lambda: restore_module.restore_latest(live.context(), clock=now)):
            with pytest.raises(PocError, match="|".join(patterns)):
                call()
        assert live.psql("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'").strip() != "0", label  # nothing touched
        assert _healthy(live), label

    # 1. A manifest edited inside a real snapshot, tagged with the genuine digest, published under the genuine digest.
    forged = dict(manifest, counts={**manifest["counts"], "jobs": manifest["counts"]["jobs"] + 7})
    forged_raw = (json.dumps(forged, indent=2, sort_keys=True) + "\n").encode()
    forged_id = _store_snapshot(live, forged_raw, genuine.manifest_sha256)
    forged_ref = _publish(live, forged_id, genuine.manifest_sha256, forged)
    refused("edited manifest in the snapshot", "incomplete or changed", "does not match")
    # The two checks that sit behind latest_ref are exercised directly with the genuine digest:
    with pytest.raises(PocError, match="does not match the published digest"):
        restore_module.restore_latest(live.context(), clock=now, ref=forged_ref)
    with pytest.raises(PocError, match="does not match the published digest"):
        verify_module.verify_snapshot(live.context(), forged_ref)
    with pytest.raises(PocError, match="does not match the published digest"):
        lifecycle.load_manifest(live.context(), forged_ref)

    # 2. latest.json edited: truncated, a different digest, a different snapshot.
    pointer = json.loads(good_pointer)
    (live.folder / "latest.json").write_text(good_pointer[: len(good_pointer) // 2])
    refused("truncated latest.json", "unreadable")
    (live.folder / "latest.json").write_text(json.dumps({**pointer, "snapshot_id": forged_id, "manifest_sha256": "0" * 64}))
    refused("edited digest in latest.json", "incomplete or changed")
    (live.folder / "latest.json").write_text(json.dumps({**pointer, "snapshot_id": genuine.snapshot_id}))
    refused("latest.json names an older real snapshot", "latest backup changed")  # the repository's newest is the forged one

    # 3. The "incomplete" branch: right digest and bytes, but the snapshot does not carry the manifest tag.
    untagged = _store_snapshot(live, genuine_raw, "f" * 64)
    _publish(live, untagged, genuine.manifest_sha256, manifest)
    refused("snapshot without its manifest tag", "incomplete or changed")
    for label, raw, expected in (("not json", b"this is not json", "unreadable"),
                                 ("missing fields", b'{"stack": "' + live.name.encode() + b'"}', "incomplete")):
        snapshot = _store_snapshot(live, raw, hashlib.sha256(raw).hexdigest())
        (live.folder / "latest.json").write_text(json.dumps({**pointer, "snapshot_id": snapshot,
                                                             "manifest_sha256": hashlib.sha256(raw).hexdigest()}))
        refused(label, expected)

    # 4. The genuine state still works: publish it again as a fresh backup.
    fresh = _backup(live)
    assert lifecycle.catalog.latest_ref(live.context()).snapshot_id == fresh.snapshot_id
    verify_module.verify_snapshot(live.context(), fresh)


@pytest.fixture(scope="module")
def journey(poc_stack):
    """seed -> backup -> checked down -> up (restore). Everything the three journey tests read is captured here."""
    live = poc_stack
    key = live.api_key()
    live.seed_decisions(3)
    live.compose("stop", "worker")  # queued work stays queued: the worker is what must resume it after the restore
    queued = live.ingest(key, "    \n")["job_id"]
    leased = live.ingest(key, "     \n")["job_id"]
    live.psql(f"UPDATE jobs SET status = 'running', attempts = 1, locked_by = 'dead-worker', "
              f"lease_until = now() - interval '1 hour' WHERE id = '{leased}'")
    tenant = live.tenant()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cap_micro = round(config.DEFAULT_DAILY_COST_CAP_USD * limits.MICRO_USD)
    for name, value in ((f"cost:{tenant}:{today}", str(cap_micro)), ("websess:old-session", "1"), ("rl:old-window", "1"),
                        ("cache:old-entry", "1")):
        live.valkey("SET", name, value)
    ref = _backup(live)
    manifest = lifecycle.load_manifest(live.context(), ref)
    jobs_in_snapshot = int(manifest["counts"]["jobs"])
    environ = {**os.environ, "POC_RECOVERY_REF": ref.snapshot_id}
    lifecycle.down(ROOT, live.name, runner=LocalRunner(), environ=environ)
    after_down = SimpleNamespace(
        volumes=_volumes_exist(live),
        kept={n: (live.folder / n).exists() for n in ("receipt-signing.key", "restic-password", "marker.json", "latest.json",
                                                         "backups/config")},
        containers=subprocess.run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={live.project}",
                                   "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split(),
    )
    marker = up(ROOT, live.name, runner=LocalRunner())
    assert marker == live.marker
    return SimpleNamespace(live=live, key=key, ref=ref, manifest=manifest, queued=queued, leased=leased, tenant=tenant,
                           today=today, cap_micro=cap_micro, after_down=after_down, jobs_in_snapshot=jobs_in_snapshot)


def test_restore_reproduces_manifest_before_writers(journey):
    live, manifest = journey.live, journey.manifest
    assert not any(journey.after_down.volumes.values()) and journey.after_down.containers == []
    assert all(journey.after_down.kept.values()), journey.after_down.kept  # secrets, marker, pointer and repository survive
    report = json.loads((live.folder / "restore-report.json").read_text())
    assert report["snapshot_id"] == journey.ref.snapshot_id and report["manifest_sha256"] == journey.ref.manifest_sha256
    assert report["verified_state"]["counts"] == manifest["counts"]  # compared to the manifest before any writer ran
    assert report["verified_state"]["heads"] == manifest["heads"] and report["verified_state"]["checkpoints"] == manifest["checkpoints"]
    assert report["objects_verified"] == len(manifest["objects"]) and report["objects_verified"] >= 2
    assert report["verified_at"] <= report["writers_started_at"]
    assert _healthy(live)
    for obj in manifest["objects"]:  # the object bytes are back in the new volume and still hash to their key
        out = subprocess.run([*live.context().base, "exec", "-T", "api", "cat", f"/data/objects/{obj['key'][:2]}/{obj['key']}"],
                             cwd=ROOT, env=live.context().env, capture_output=True, check=True).stdout
        assert hashlib.sha256(out).hexdigest() == obj["key"]
    # A repeated up never restores over current data.
    key = journey.key
    extra = live.ingest(key, "      \n")["job_id"]
    stamp = (live.folder / "restore-report.json").stat().st_mtime_ns
    up(ROOT, live.name, runner=LocalRunner())
    assert (live.folder / "restore-report.json").stat().st_mtime_ns == stamp
    assert extra in live.psql("SELECT id FROM jobs").split()



def test_valkey_loss_and_postgres_work_recovery(journey):
    live = journey.live
    report = json.loads((live.folder / "restore-report.json").read_text())
    for lost in ("rate_limit_windows", "cache_entries", "sessions", "token_counters", "breaker_state", "leases"):
        assert lost in report["valkey_lost"]
    for old in ("websess:old-session", "rl:old-window", "cache:old-entry"):
        assert live.valkey("GET", old).strip() in ("", "(nil)")  # invalidated: the old session must sign in again
    key = journey.key
    queued = live.wait_job(key, journey.queued)
    leased = live.wait_job(key, journey.leased)
    assert queued["status"] == "succeeded" and queued["attempts"] == 1  # a queued job survived in Postgres
    assert leased["status"] == "succeeded" and leased["attempts"] == 2  # the expired lease was reclaimed, once
    assert live.psql(f"SELECT count(*) FROM jobs WHERE id IN ('{journey.queued}', '{journey.leased}')").strip() == "2"  # no dupes
    assert report["non_durable_work_lost"] == []  # nothing pending lived only in Valkey; if it did, it would be listed here


def test_valkey_loss_does_not_reset_spending_authority(journey):
    live = journey.live
    report = json.loads((live.folder / "restore-report.json").read_text())
    cost_key = f"cost:{journey.tenant}:{journey.today}"
    assert report["cost_counters_restored"] == {cost_key: journey.cap_micro}
    assert int(live.valkey("GET", cost_key)) == journey.cap_micro

    async def get(name):
        return live.valkey("GET", name).strip() or None

    runtime = SimpleNamespace(cache=SimpleNamespace(get=get))
    result = asyncio.run(limits.check_cost(runtime, UUID(journey.tenant), None))
    assert result.exceeded  # a tenant at its cap is still denied after Valkey was lost


# --- fix round 1 (CRITICAL): a failed restore is durable and resumable; an empty stack never starts ------------------------

class FaultRunner(LocalRunner):
    """Runs every command for real; once `fault` matches a command, that command is run and then reported as failed.
    The Runner is a public seam, so no product code knows about the fault. Records every argv."""

    def __init__(self, fault):
        self.fault, self.calls = fault, []

    def run(self, argv, **kwargs):
        argv = list(argv)
        self.calls.append(argv)
        result = super().run(argv, **kwargs)
        if self.fault is not None and self.fault(argv):
            self.fault = None  # one failure only
            raise CommandError(argv, 1, b"injected fault")
        return result

    def started_writers(self) -> bool:
        return any(c[:2] == ["docker", "compose"] and "up" in c and "api" in c and "worker" in c for c in self.calls) or \
            any("alembic" in c and "upgrade" in c for c in self.calls)


def test_failed_restore_is_resumed_by_up_and_never_starts_an_empty_stack():
    from tests.integration.poc.conftest import start_live_stack, stop_live_stack

    live = start_live_stack("r")
    name = live.name
    try:
        key = live.api_key()
        live.seed_decisions(3)
        assert live.wait_job(key, live.ingest(key, "   \n")["job_id"])["status"] == "succeeded"
        tenant = live.tenant()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cost_key, spent = f"cost:{tenant}:{today}", "1000000"
        live.valkey("SET", cost_key, spent)
        ref = _backup(live)
        manifest = lifecycle.load_manifest(live.context(), ref)
        pointer_before = (live.folder / "latest.json").read_text()
        lifecycle.down(ROOT, name, runner=LocalRunner(), environ={**os.environ, "POC_RECOVERY_REF": ref.snapshot_id})
        assert not any(_volumes_exist(live).values())
        pending = live.folder / "restore-pending.json"

        def assert_no_writer_ever(runner, label):
            assert not runner.started_writers(), f"{label}: api and worker (or alembic) ran on a partial restore"
            assert set(live.services()) <= {"postgres", "valkey"}, label  # no api or worker container exists
            assert pending.is_file(), label
            body = json.loads(pending.read_text())
            assert (body["snapshot_id"], body["manifest_sha256"]) == (ref.snapshot_id, ref.manifest_sha256)

        # Fault 1: pg_restore ran, then failed. The database holds the restored tables; the marker must remain.
        first = FaultRunner(lambda argv: "pg_restore" in argv)
        with pytest.raises(PocError):
            up(ROOT, name, runner=first)
        assert_no_writer_ever(first, "after the pg_restore fault")
        with pytest.raises(PocError, match="restore is pending"):
            lifecycle.backup(ROOT, name, runner=LocalRunner(), environ=dict(os.environ))  # `latest` cannot move to a partial state
        assert (live.folder / "latest.json").read_text() == pointer_before

        # Fault 2: a resume that fails after the cost counters were applied. The retry must not apply them twice.
        second = FaultRunner(lambda argv: "valkey-cli" in argv and "EXPIRE" in argv)
        with pytest.raises((PocError, CommandError)):  # (the CLI reports either as a refusal)
            up(ROOT, name, runner=second)
        assert_no_writer_ever(second, "after the counter fault")
        assert not any("alembic" in c and "upgrade" in c for c in second.calls)

        # The re-run completes from the same snapshot.
        third = FaultRunner(None)
        marker = up(ROOT, name, runner=third)
        assert marker == live.marker
        assert not pending.exists()
        assert _healthy(live)
        report = json.loads((live.folder / "restore-report.json").read_text())
        assert report["snapshot_id"] == ref.snapshot_id and report["manifest_sha256"] == ref.manifest_sha256
        assert report["verified_state"]["counts"] == manifest["counts"]
        assert report["verified_state"]["heads"] == manifest["heads"] and report["verified_state"]["checkpoints"] == manifest["checkpoints"]
        assert report["verified_at"] <= report["writers_started_at"]
        assert int(live.psql("SELECT count(*) FROM jobs")) >= int(manifest["counts"]["jobs"])
        assert not any("alembic" in c and "upgrade" in c for c in third.calls)  # a resume never runs the normal path
        if manifest["cost_counters"]["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d"):  # (a midnight crossing skips it)
            assert live.valkey("GET", cost_key).strip() == spent, "the daily counter was applied twice or lost"
        container = live.compose("ps", "-q", "api").text.strip()
        started = subprocess.run(["docker", "inspect", "--format", "{{.State.StartedAt}}", container],
                                 capture_output=True, text=True, check=True).stdout.strip()
        assert datetime.fromisoformat(started.replace("Z", "+00:00").split(".")[0] + "+00:00") >= \
            datetime.fromisoformat(report["verified_at"]).replace(microsecond=0)  # the api started after the verification
    finally:
        stop_live_stack(live, name)
