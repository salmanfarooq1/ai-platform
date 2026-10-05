"""Sprint 008, A2: signed receipts and the decision hash chain, on real Postgres and Redis through the real app.

A valid receipt verifies offline with `scripts/verify/receipt.py` (run as its own process). A tampered decision, signature
or chain link each fails, in the script and in the server's verify route alike. Concurrent decision writes of one tenant
still give one unbroken chain. The chain and the receipt never hold input text.
"""
import asyncio
import base64
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway import record
from tests.e2e.web_helpers import bearer, insert_decision, key_with

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify" / "receipt.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_receipt_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


offline = _load_script()


@pytest.fixture
async def audit(make_client, tenant_a, database_url):
    token, _ = key_with(database_url, tenant_a, ["audit:read"])
    return make_client(bearer(token))


@pytest.fixture
async def audit_b(make_client, tenant_b, database_url):
    token, _ = key_with(database_url, tenant_b, ["audit:read"])
    return make_client(bearer(token))


async def a_decision_id(audit, tenant, pool) -> str:
    """The id of one recorded, chained decision of the tenant (the audit read of an earlier call)."""
    assert (await audit.get("/v1/decisions")).status_code == 200
    row = await pool.fetchrow(
        "SELECT id FROM gateway_decisions WHERE tenant_id = $1 AND chain_position IS NOT NULL ORDER BY chain_position LIMIT 1",
        UUID(tenant.id),
    )
    assert row is not None
    return str(row["id"])


async def keys_of(audit) -> dict[str, bytes]:
    body = (await audit.get("/v1/receipts/keys")).json()
    return {k["key_id"]: base64.b64decode(k["public_key"]) for k in body}


def failing(checks) -> set[str]:
    return {name for name, ok, _ in checks if not ok}


# ------------------------------------------------------------------ a valid receipt, offline

async def test_a_valid_receipt_verifies_offline_with_the_script(audit, tenant_a, pool, tmp_path):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    keys = (await audit.get("/v1/receipts/keys")).json()
    assert receipt["alg"] == "Ed25519" and receipt["key_id"] == keys[0]["key_id"] and keys[0]["active"] is True
    (tmp_path / "receipt.json").write_text(json.dumps(receipt))
    (tmp_path / "keys.json").write_text(json.dumps(keys))
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "receipt", str(tmp_path / "receipt.json"), "--keys", str(tmp_path / "keys.json")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip().endswith("VALID") and "[FAIL]" not in run.stdout
    # one public key on its own also works
    one = subprocess.run(
        [sys.executable, str(SCRIPT), "receipt", str(tmp_path / "receipt.json"), "--public-key", keys[0]["public_key"]],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert one.returncode == 0, one.stdout


async def test_the_receipt_carries_the_contract_fields_and_the_server_verifies_it(audit, tenant_a, pool):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    assert set(receipt) == {"decision", "chain", "signature", "key_id", "alg", "canonical"}
    assert set(receipt["chain"]) == {"prev_hash", "row_hash", "position"} and receipt["chain"]["position"] >= 1
    assert receipt["decision"]["id"] == decision_id
    signed = json.loads(receipt["canonical"])
    assert signed["decision"]["id"] == decision_id and signed["chain"] == receipt["chain"]
    result = (await audit.post("/v1/receipts/verify", json=receipt)).json()
    assert result["valid"] is True
    assert [c["name"] for c in result["checks"]] == ["alg", "key", "canonical", "signature", "row_hash"]
    assert all(c["ok"] for c in result["checks"])


# ------------------------------------------------------------------ tampering

def tampered(receipt: dict, how: str) -> dict:
    bad = copy.deepcopy(receipt)
    if how == "decision":  # an edited decision, canonical and signature left alone
        bad["decision"]["outcome"] = "deny" if bad["decision"]["outcome"] == "allow" else "allow"
    elif how == "decision_and_canonical":  # the attacker also rewrites the signed text
        bad["decision"]["reason"] = "forged"
        signed = json.loads(bad["canonical"])
        signed["decision"]["reason"] = "forged"
        bad["canonical"] = json.dumps(signed, sort_keys=True, separators=(",", ":"))
    elif how == "signature":
        raw = bytearray(base64.b64decode(bad["signature"]))
        raw[0] ^= 0xFF
        bad["signature"] = base64.b64encode(bytes(raw)).decode()
    elif how == "prev_hash":
        bad["chain"]["prev_hash"] = "0" * 64
    elif how == "row_hash":
        bad["chain"]["row_hash"] = "f" * 64
    elif how == "position":
        bad["chain"]["position"] += 1
    elif how == "key":
        bad["key_id"] = "0000000000000000"
    return bad


@pytest.mark.parametrize("how, expect", [
    ("decision", {"canonical", "row_hash"}),
    ("decision_and_canonical", {"signature", "row_hash"}),
    ("signature", {"signature"}),
    # the signature is over the text as signed, so an edit outside it breaks the other checks, not the signature
    ("prev_hash", {"canonical", "row_hash"}),
    ("row_hash", {"canonical", "row_hash"}),
    ("position", {"canonical"}),
    ("key", {"key", "signature"}),
])
async def test_a_tampered_receipt_fails_in_the_script_and_on_the_server_alike(audit, tenant_a, pool, how, expect):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    keys = await keys_of(audit)
    bad = tampered(receipt, how)
    offline_failed = failing(offline.verify_receipt(bad, keys))
    assert offline_failed == expect, (how, offline_failed)
    verdict = (await audit.post("/v1/receipts/verify", json=bad)).json()
    assert verdict["valid"] is False
    assert {c["name"] for c in verdict["checks"] if not c["ok"]} == expect  # the server runs the same checks


async def test_the_script_exits_1_for_a_tampered_receipt(audit, tenant_a, pool, tmp_path):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    keys = (await audit.get("/v1/receipts/keys")).json()
    (tmp_path / "receipt.json").write_text(json.dumps(tampered(receipt, "decision")))
    (tmp_path / "keys.json").write_text(json.dumps(keys))
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "receipt", str(tmp_path / "receipt.json"), "--keys", str(tmp_path / "keys.json")],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert run.returncode == 1 and "INVALID" in run.stdout and "[FAIL]" in run.stdout


async def test_a_receipt_signed_by_another_key_is_invalid(audit, tenant_a, pool, app):
    """A receipt signed with a key the platform does not list fails, even when everything else is consistent."""
    from gateway.receipts import Keyring, sign_receipt

    decision_id = await a_decision_id(audit, tenant_a, pool)
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    from gateway.receipts import record_of

    forged = {**receipt, **sign_receipt(Keyring.generate(), record_of(receipt["decision"]), receipt["chain"])}
    verdict = (await audit.post("/v1/receipts/verify", json=forged)).json()
    assert verdict["valid"] is False and {c["name"] for c in verdict["checks"] if not c["ok"]} == {"key", "signature"}


async def test_old_keys_stay_listed_after_a_rotation_so_old_receipts_still_verify(audit, tenant_a, pool, app):
    from gateway.receipts import Keyring

    decision_id = await a_decision_id(audit, tenant_a, pool)
    old = app.state.receipt_keys
    receipt = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    old_public = base64.b64decode(next(k.public_key for k in old.public_keys() if k.active))
    app.state.receipt_keys = Keyring.generate(previous_public=[old_public])  # the rotation
    keys = (await audit.get("/v1/receipts/keys")).json()
    assert [k["active"] for k in keys] == [True, False] and {k["key_id"] for k in keys} >= {receipt["key_id"]}
    assert all(set(k) == {"key_id", "alg", "public_key", "active"} for k in keys)  # no secret field
    assert (await audit.post("/v1/receipts/verify", json=receipt)).json()["valid"] is True
    fresh = (await audit.get(f"/v1/receipts/{decision_id}")).json()
    assert fresh["key_id"] != receipt["key_id"] and (await audit.post("/v1/receipts/verify", json=fresh)).json()["valid"] is True


# ------------------------------------------------------------------ access

async def test_foreign_and_missing_decisions_give_an_identical_404(audit, audit_b, tenant_a, pool):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    foreign = await audit_b.get(f"/v1/receipts/{decision_id}")
    missing = await audit_b.get(f"/v1/receipts/{uuid4()}")
    garbage = await audit_b.get("/v1/receipts/not-a-uuid")
    assert foreign.status_code == missing.status_code == garbage.status_code == 404
    strip = lambda r: {**r.json()["error"], "request_id": None}  # noqa: E731 - the request id differs by design
    assert strip(foreign) == strip(missing) == strip(garbage)


async def test_receipt_routes_need_audit_read_and_leave_a_decision_row(client, audit, tenant_a, pool):
    for method, path in (("get", "/v1/receipts/keys"), ("get", f"/v1/receipts/{uuid4()}"), ("get", "/v1/trust/summary")):
        assert (await getattr(client, method)(path)).status_code == 403  # the full key has no audit:read
    assert (await client.post("/v1/receipts/verify", json={})).status_code == 403
    before = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE resource = 'receipts'")
    assert (await audit.get("/v1/receipts/keys")).status_code == 200
    assert (await audit.get(f"/v1/receipts/{uuid4()}")).status_code == 404
    after = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE resource = 'receipts' AND action = 'audit.read'")
    assert after == before + 2


async def test_a_decision_from_before_receipts_existed_has_no_receipt(audit, tenant_a, pool):
    legacy = await insert_decision(pool, tenant_a, request_id="old")  # inserted without a chain link
    response = await audit.get(f"/v1/receipts/{legacy}")
    assert response.status_code == 409 and response.json()["error"]["code"] == "receipt_unavailable"


# ------------------------------------------------------------------ the chain

def export_chain(dsn: str, tenant) -> dict:
    return offline.export_from_database(dsn, tenant.id)


async def test_concurrent_decision_writes_of_one_tenant_give_one_unbroken_chain(audit, tenant_a, pool, database_url):
    responses = await asyncio.gather(*(audit.get("/v1/policies") for _ in range(40)))
    assert all(r.status_code == 200 for r in responses)
    export = await asyncio.to_thread(export_chain, database_url, tenant_a)
    positions = [r["position"] for r in export["rows"]]
    assert len(positions) >= 40 and positions == list(range(1, len(positions) + 1))  # no gap, no repeat
    checks = offline.verify_chain(export)
    assert all(ok for _, ok, _ in checks), checks
    assert export["rows"][0]["prev_hash"] == offline.genesis_hash(tenant_a.id)
    # the server-side module agrees with the standalone script
    from gateway.chain import ChainRow, verify_chain

    rows = [ChainRow(r["position"], r["prev_hash"], r["row_hash"], r["decision"]) for r in export["rows"]]
    assert all(c.ok for c in verify_chain(rows, {0: offline.genesis_hash(tenant_a.id)}))
    # and the head holds the last link
    head = await pool.fetchrow("SELECT position, row_hash FROM chain_heads WHERE tenant_id = $1", UUID(tenant_a.id))
    assert (head["position"], head["row_hash"]) == (positions[-1], export["rows"][-1]["row_hash"])


async def test_two_tenants_have_separate_chains(audit, audit_b, tenant_a, tenant_b, database_url):
    await asyncio.gather(*(c.get("/v1/policies") for c in (audit, audit_b) for _ in range(5)))
    a = await asyncio.to_thread(export_chain, database_url, tenant_a)
    b = await asyncio.to_thread(export_chain, database_url, tenant_b)
    assert a["rows"][0]["prev_hash"] == offline.genesis_hash(tenant_a.id) != b["rows"][0]["prev_hash"]
    assert all(ok for _, ok, _ in offline.verify_chain(a)) and all(ok for _, ok, _ in offline.verify_chain(b))
    assert {r["decision"]["tenant_id"] for r in a["rows"]} == {tenant_a.id}


@pytest.mark.parametrize("change", [
    "UPDATE gateway_decisions SET outcome = 'deny' WHERE chain_position = 2",          # an edited decision
    "UPDATE gateway_decisions SET prev_hash = repeat('0', 64) WHERE chain_position = 3",  # a cut link
    "UPDATE gateway_decisions SET row_hash = repeat('a', 64) WHERE chain_position = 2",   # a rewritten hash
    "DELETE FROM gateway_decisions WHERE chain_position = 2",                              # a removed row
])
async def test_the_chain_check_sees_an_edit_a_cut_link_and_a_removed_row(audit, tenant_a, pool, database_url, change):
    for _ in range(5):
        assert (await audit.get("/v1/policies")).status_code == 200
    assert all(ok for _, ok, _ in offline.verify_chain(await asyncio.to_thread(export_chain, database_url, tenant_a)))
    await pool.execute(change)
    checks = offline.verify_chain(await asyncio.to_thread(export_chain, database_url, tenant_a))
    assert failing(checks), change


async def test_a_stored_decision_that_was_edited_gets_no_receipt(audit, tenant_a, pool):
    decision_id = await a_decision_id(audit, tenant_a, pool)
    await pool.execute("UPDATE gateway_decisions SET reason = 'edited' WHERE id = $1", UUID(decision_id))
    response = await audit.get(f"/v1/receipts/{decision_id}")
    assert response.status_code == 409 and response.json()["error"]["code"] == "chain_mismatch"


async def test_the_script_checks_a_chain_straight_from_postgres(audit, tenant_a, database_url, tmp_path):
    for _ in range(3):
        await audit.get("/v1/policies")
    run = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, str(SCRIPT), "chain", "--dsn", database_url, "--tenant", tenant_a.id, "--export", str(tmp_path / "c.json")],
        capture_output=True, text=True,
    )
    assert run.returncode == 0 and run.stdout.strip().endswith("VALID"), run.stdout + run.stderr
    again = subprocess.run([sys.executable, str(SCRIPT), "chain", "--file", str(tmp_path / "c.json")], capture_output=True, text=True)
    assert again.returncode == 0


# ------------------------------------------------------------------ fail closed, and no input text

async def test_a_failed_chain_step_fails_an_allow_closed_but_a_deny_keeps_its_row(
    make_client, tenant_a, pool, database_url, monkeypatch, audit,
):
    async def broken(*args, **kwargs):
        raise RuntimeError("chain step failed")

    monkeypatch.setattr(record, "_insert_chained", broken)
    before = await pool.fetchval("SELECT count(*) FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id))
    allowed = await audit.get("/v1/policies")  # the allow cannot be recorded
    assert allowed.status_code == 503 and allowed.json()["error"]["code"] == "decision_unrecorded"
    reader = make_client(tenant_a.headers("reader"))  # kb:read only: audit.read is denied at the boundary
    denied = await reader.get("/v1/policies")
    assert denied.status_code in (401, 403)
    rows = await pool.fetch(
        "SELECT outcome, chain_position, row_hash FROM gateway_decisions WHERE tenant_id = $1 ORDER BY created_at",
        UUID(tenant_a.id),
    )
    assert len(rows) == before + 1  # the allow wrote nothing, the deny kept its row
    assert rows[-1]["outcome"] == "deny" and rows[-1]["chain_position"] is None and rows[-1]["row_hash"] is None


async def test_neither_the_chain_nor_a_receipt_ever_holds_input_text(make_client, tenant_a, database_url, pool, audit, fake_llm, fake_embeddings):
    secret_question = "what is the zebra-quartz-7731 retention rule?"
    ingest = await make_client(tenant_a.headers("full")).post(
        "/v1/ingest", data={"namespace": "legal"}, files={"file": ("a.txt", b"retention rules for records " * 5, "text/plain")},
    )
    assert ingest.status_code == 202
    search = await make_client(tenant_a.headers("full")).post("/v1/search", json={"query": secret_question, "namespace": "legal"})
    assert search.status_code in (200, 404)
    row = await pool.fetchrow(
        "SELECT id, input_hash FROM gateway_decisions WHERE tenant_id = $1 AND input_hash IS NOT NULL AND chain_position IS NOT NULL "
        "ORDER BY chain_position LIMIT 1", UUID(tenant_a.id))
    assert row is not None
    receipt_text = (await audit.get(f"/v1/receipts/{row['id']}")).text
    export_text = json.dumps(await asyncio.to_thread(export_chain, database_url, tenant_a))
    columns = await pool.fetch("SELECT * FROM gateway_decisions WHERE tenant_id = $1", UUID(tenant_a.id))
    for text in (receipt_text, export_text, json.dumps([dict(c) for c in columns], default=str)):
        assert "zebra-quartz-7731" not in text
    assert json.loads(receipt_text)["decision"]["input_sha256"] == row["input_hash"]
