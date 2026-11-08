#!/usr/bin/env python3
"""Verify an audit receipt, or a tenant's decision chain, offline (Sprint 008, ADR-0012).

This file stands alone on purpose. It imports nothing from the platform: only the standard library and
`cryptography` (and `psycopg2`, only for `chain --dsn`). An auditor can copy it, a receipt and a public key to a machine
that never talks to the platform and check them there.

    receipt.py receipt RECEIPT.json --public-key BASE64          one key
    receipt.py receipt RECEIPT.json --keys KEYS.json             the output of GET /v1/receipts/keys
    receipt.py chain --file CHAIN.json --keys KEYS.json          a chain export (see below)
    receipt.py chain --dsn DSN --tenant TENANT_UUID --keys KEYS.json [--export CHAIN.json]

A receipt is what `GET /v1/receipts/{decision_id}` returns. The receipt checks are:
  alg        the algorithm is Ed25519
  key        the key_id is one of the keys you gave
  canonical  the signed text is the one the decision and chain fields give (a changed field shows here)
  signature  the Ed25519 signature is valid over the signed text
  row_hash   row_hash = sha256(canonical_json(decision record) || prev_hash)

A chain export is JSON: {"tenant_id", "checkpoints": [{"position", "row_hash", "reason", "signature", "key_id"}], "rows": [{"position", "prev_hash",
"row_hash", "decision": {...record...}}]}. The chain checks are: each row_hash matches its record, each row points at
the row before it (the first at the checkpoint just before it: position 0 is sha256("genesis:<tenant id>"), a purge
leaves a signed checkpoint), and positions have no gaps. A purge checkpoint must carry a valid signature of one of the keys
you give: an unsigned or badly signed checkpoint fails, and so does a chain that has purge checkpoints when no key is given.

Exit status: 0 when every check passes, 1 when one fails, 2 for a usage or input error. The output never contains input
text: a decision holds only the SHA-256 of its input.
"""
import argparse
import base64
import binascii
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ALG = "Ed25519"
RECORD_FIELDS = (
    "id", "tenant_id", "principal_id", "request_id", "action", "resource", "outcome", "stage", "reason",
    "policy_version", "input_sha256", "execution_id", "created_at",
)


# ----------------------------------------------------------------------------- the same rules as evidence/chain.py

def _versioned(record: dict[str, Any], version: Any, extensions: Any) -> dict[str, Any]:
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported decision record version")
    if not isinstance(extensions, Mapping):
        raise ValueError("extensions must be a JSON object")
    if version == 1 and extensions:
        raise ValueError("version 1 cannot carry unsigned extensions")
    # The reviewed registry is empty in Sprint 012, in both the server and this
    # standalone verifier. A later registered schema must update both verifiers.
    if extensions:
        raise ValueError("extension key is not registered")
    if version == 2:
        record.update(record_version=2, extensions={})
    return record

def format_time(value: Any) -> str:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def decision_record(decision: dict[str, Any]) -> dict[str, Any]:
    """The record that is hashed, from a receipt's `decision` object (the console's decision detail)."""
    principal = decision.get("principal")
    record = {
        "id": str(decision["id"]), "tenant_id": str(decision["tenant"]["id"]),
        "principal_id": _text((principal or {}).get("id")), "request_id": decision["request_id"],
        "action": decision["action"], "resource": decision.get("resource"), "outcome": decision["outcome"],
        "stage": decision["stage"], "reason": decision["reason"], "policy_version": decision.get("policy_version"),
        "input_sha256": decision.get("input_sha256"), "execution_id": _text(decision.get("execution_id")),
        "created_at": format_time(decision["created_at"]),
    }
    return _versioned(record, decision.get("record_version", 1), decision.get("extensions", {}))


def normalize_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project the signed fields rather than hashing API defaults into old rows."""
    if set(value) - {*RECORD_FIELDS, "record_version", "extensions"}:
        raise ValueError("unsupported canonical decision field")
    record = {key: value[key] for key in RECORD_FIELDS}
    for key in ("id", "tenant_id"):
        record[key] = str(record[key])
    for key in ("principal_id", "execution_id"):
        record[key] = _text(record[key])
    record["created_at"] = format_time(record["created_at"])
    return _versioned(record, value.get("record_version", 1), value.get("extensions", {}))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def row_hash_of(record: dict[str, Any], prev_hash: str) -> str:
    return hashlib.sha256(canonical_json(record).encode("utf-8") + prev_hash.encode("ascii")).hexdigest()


def genesis_hash(tenant_id: str) -> str:
    return hashlib.sha256(f"genesis:{tenant_id}".encode()).hexdigest()


def key_id_of(public_raw: bytes) -> str:
    return hashlib.sha256(public_raw).hexdigest()[:16]


# ----------------------------------------------------------------------------- receipt

def verify_receipt(receipt: dict[str, Any], keys: dict[str, bytes]) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    try:
        record = decision_record(receipt["decision"])
        chain = receipt["chain"]
        rebuilt = canonical_json({
            "chain": {"prev_hash": chain["prev_hash"], "row_hash": chain["row_hash"], "position": chain["position"]},
            "decision": record,
        })
        prev_hash, row_hash, parsed = str(chain["prev_hash"]), str(chain["row_hash"]), True
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        record, rebuilt, prev_hash, row_hash, parsed = {}, "", "", "", False
    alg = receipt.get("alg")
    checks.append(("alg", alg == ALG, f"algorithm {alg}" if alg == ALG else f"algorithm {alg!r} is not {ALG}"))
    key_id = str(receipt.get("key_id"))
    raw = keys.get(key_id)
    checks.append(("key", raw is not None, f"key {key_id} is known" if raw else f"key {key_id} is not one of the keys given"))
    canonical = receipt.get("canonical")
    same = parsed and canonical == rebuilt
    checks.append(("canonical", same, "the signed text matches the decision and chain fields" if same
                   else "the decision or chain fields do not match the signed text"))
    ok, detail = False, "no key to check against"
    if raw is not None and isinstance(canonical, str):
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(
                base64.b64decode(str(receipt.get("signature")), validate=True), canonical.encode("utf-8"))
            ok, detail = True, "the signature is valid"
        except (InvalidSignature, binascii.Error, ValueError, TypeError):
            detail = "the signature does not match the signed text"
    checks.append(("signature", ok, detail))
    try:
        hash_ok = parsed and row_hash_of(record, prev_hash) == row_hash
    except (TypeError, ValueError):
        hash_ok = False
    checks.append(("row_hash", hash_ok, "the row hash is the hash of the decision and the previous hash" if hash_ok
                   else "the row hash does not match the decision and the previous hash"))
    return checks


def load_keys(args: argparse.Namespace) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    if args.public_key:
        raw = base64.b64decode(args.public_key, validate=True)
        keys[key_id_of(raw)] = raw
    if args.keys:
        for item in json.loads(Path(args.keys).read_text(encoding="utf-8")):
            raw = base64.b64decode(item["public_key"], validate=True)
            keys[str(item.get("key_id") or key_id_of(raw))] = raw
    if not keys:
        raise SystemExit("error: give --public-key or --keys")
    return keys


# ----------------------------------------------------------------------------- chain

def checkpoint_text(tenant: str, position: int, row_hash: str, reason: str) -> str:
    return canonical_json({"tenant_id": tenant, "position": int(position), "row_hash": row_hash, "reason": reason})


def verify_checkpoints(export: dict[str, Any], keys: dict[str, bytes]) -> tuple[str, bool, str]:
    """Every purge checkpoint must be signed with a key you gave. Position 0 is derived from the tenant id: no signature."""
    tenant = str(export["tenant_id"])
    problems = []
    for cp in export.get("checkpoints", []):
        if cp.get("reason") == "genesis" or int(cp["position"]) == 0:
            continue
        raw = keys.get(str(cp.get("key_id")))
        if not cp.get("signature") or raw is None:
            problems.append(f"checkpoint {cp['position']} is unsigned, or its key was not given")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(
                base64.b64decode(str(cp["signature"]), validate=True),
                checkpoint_text(tenant, int(cp["position"]), str(cp["row_hash"]), "purge").encode("utf-8"))
        except (InvalidSignature, binascii.Error, ValueError):
            problems.append(f"checkpoint {cp['position']} has a bad signature")
    return ("checkpoints", not problems, "; ".join(problems) or "every purge checkpoint is signed")


def verify_chain(export: dict[str, Any], keys: dict[str, bytes] | None = None) -> list[tuple[str, bool, str]]:
    tenant = str(export["tenant_id"])
    anchors = {0: genesis_hash(tenant)}
    anchors.update({int(c["position"]): str(c["row_hash"]) for c in export.get("checkpoints", []) if int(c["position"]) != 0})
    extra = [verify_checkpoints(export, keys or {})]
    rows = sorted(export["rows"], key=lambda r: int(r["position"]))
    if not rows:
        return [*extra, ("chain_rows", True, "no rows to check")]
    bad_hash: list[str] = []
    bad_link: list[str] = []
    gaps: list[str] = []
    first = int(rows[0]["position"])
    anchor = anchors.get(first - 1)
    if anchor is None:
        bad_link.append(f"no checkpoint at position {first - 1}")
    elif rows[0]["prev_hash"] != anchor:
        bad_link.append(f"position {first} does not follow the checkpoint at {first - 1}")
    previous = rows[0]
    for row in rows:
        position = int(row["position"])
        try:
            record = normalize_record(row["decision"])
            if str(record.get("tenant_id")) != tenant:
                bad_hash.append(f"position {position}: the decision belongs to another tenant")
            hash_ok = row_hash_of(record, row["prev_hash"]) == row["row_hash"]
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
            hash_ok = False
        if not hash_ok:
            bad_hash.append(f"position {position}: the row hash does not match its record")
        if row is not rows[0]:
            if position != int(previous["position"]) + 1:
                gaps.append(f"position {previous['position']} is followed by {position}")
            elif row["prev_hash"] != previous["row_hash"]:
                bad_link.append(f"position {position} does not follow position {previous['position']}")
        previous = row
    return [
        *extra,
        ("row_hashes", not bad_hash, "; ".join(bad_hash) or f"{len(rows)} row hashes match their records"),
        ("links", not bad_link, "; ".join(bad_link) or "every row points at the row before it"),
        ("no_gaps", not gaps, "; ".join(gaps) or "positions are consecutive"),
    ]


def export_from_database(dsn: str, tenant: str) -> dict[str, Any]:
    import psycopg2  # only this mode needs it

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant,))  # row-level security for the app role
            cur.execute("SELECT position, row_hash, reason, signature, key_id FROM chain_checkpoints WHERE tenant_id = %s ORDER BY position", (tenant,))
            checkpoints = [{"position": p, "row_hash": h, "reason": r, "signature": sg, "key_id": k} for p, h, r, sg, k in cur.fetchall()]
            cur.execute(
                "SELECT chain_position, prev_hash, row_hash, id, tenant_id, principal_id, request_id, action, resource, outcome, "
                "stage, reason, policy_version, input_hash, execution_id, created_at, record_version, extensions FROM gateway_decisions "
                "WHERE tenant_id = %s AND chain_position IS NOT NULL ORDER BY chain_position", (tenant,))
            rows = []
            for (position, prev_hash, row_hash, did, tid, pid, rid, action, resource, outcome, stage, reason, version,
                 input_hash, execution_id, created_at, record_version, extensions) in cur.fetchall():
                rows.append({"position": position, "prev_hash": prev_hash, "row_hash": row_hash, "decision": normalize_record({
                    "id": str(did), "tenant_id": str(tid), "principal_id": _text(pid), "request_id": rid, "action": action,
                    "resource": resource, "outcome": outcome, "stage": stage, "reason": reason, "policy_version": version,
                    "input_sha256": input_hash, "execution_id": _text(execution_id), "created_at": format_time(created_at),
                    "record_version": record_version, "extensions": extensions})})
    finally:
        conn.close()
    return {"tenant_id": tenant, "checkpoints": checkpoints, "rows": rows}


# ----------------------------------------------------------------------------- command line

def report(title: str, checks: list[tuple[str, bool, str]]) -> int:
    print(title)
    for name, ok, detail in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
    valid = all(ok for _, ok, _ in checks)
    print("VALID" if valid else "INVALID")
    return 0 if valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("receipt", help="verify one receipt")
    r.add_argument("file", type=Path)
    r.add_argument("--public-key", help="base64 of the 32 raw public key bytes")
    r.add_argument("--keys", type=Path, help="JSON list of {key_id, public_key}, as GET /v1/receipts/keys returns")
    c = sub.add_parser("chain", help="verify a tenant's decision chain")
    c.add_argument("--public-key", help="base64 public key that signed the purge checkpoints")
    c.add_argument("--keys", type=Path, help="JSON list of {key_id, public_key} (GET /v1/receipts/keys)")
    c.add_argument("--file", type=Path, help="a chain export (JSON)")
    c.add_argument("--dsn", help="read the chain from Postgres instead")
    c.add_argument("--tenant", help="the tenant id (with --dsn)")
    c.add_argument("--export", type=Path, help="with --dsn: also write the export to this file")
    args = parser.parse_args(argv)
    try:
        if args.command == "receipt":
            receipt = json.loads(args.file.read_text(encoding="utf-8"))
            return report(f"receipt {args.file}", verify_receipt(receipt, load_keys(args)))
        if args.file:
            export = json.loads(args.file.read_text(encoding="utf-8"))
        elif args.dsn and args.tenant:
            export = export_from_database(args.dsn, args.tenant)
            if args.export:
                args.export.write_text(json.dumps(export, indent=1), encoding="utf-8")
        else:
            print("error: give --file, or --dsn with --tenant", file=sys.stderr)
            return 2
        keys = load_keys(args) if (args.public_key or args.keys) else {}
        return report(f"chain of tenant {export['tenant_id']} ({len(export['rows'])} rows)", verify_chain(export, keys))
    except (OSError, ValueError, KeyError, TypeError, binascii.Error) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
