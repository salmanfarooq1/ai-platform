"""Signed receipts: an Ed25519 signature over a decision record and its chain link (ADR-0012).

A receipt says: this decision was recorded, at this position of the tenant's chain, and the platform signed it. The
signed text (`canonical`) is the canonical JSON of `{"chain": {prev_hash, row_hash, position}, "decision": record}`,
where the record is `gateway.chain.decision_record`. It holds no input text: only the SHA-256 on the row.

Keys: the active private key comes from `RECEIPT_SIGNING_KEY` (base64, 32 raw bytes). In `local` mode with no key, a
key is generated at startup and only its `key_id` is logged; receipts signed with it stop verifying after a restart.
Old public keys (`RECEIPT_PREVIOUS_PUBLIC_KEYS`) stay in the key list, so a receipt signed before a rotation still
verifies. A `key_id` is the first 16 hex characters of the SHA-256 of the raw public key.

`verify_receipt` is what `POST /v1/receipts/verify` runs. `scripts/verify/receipt.py` runs the same checks offline.
"""
import base64
import binascii
import hashlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from gateway.chain import Check, canonical_json, compute_row_hash, decision_record

logger = logging.getLogger("gateway.receipts")

ALG = "Ed25519"


def key_id_of(public_raw: bytes) -> str:
    return hashlib.sha256(public_raw).hexdigest()[:16]


def _raw_public(key: Ed25519PublicKey) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def decode_key(text: str) -> bytes:
    """32 raw bytes from base64 text. Raises ValueError (never echoing the text)."""
    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("not valid base64") from None
    if len(raw) != 32:
        raise ValueError("an Ed25519 key is 32 bytes")
    return raw


@dataclass(frozen=True)
class PublicKeyInfo:
    key_id: str
    alg: str
    public_key: str  # base64 of the 32 raw bytes
    active: bool


class Keyring:
    """The active signing key and every public key a receipt may have been signed with."""

    def __init__(self, active: Ed25519PrivateKey, previous_public: list[bytes] | None = None) -> None:
        self._active = active
        self._active_public = _raw_public(active.public_key())
        self._active_id = key_id_of(self._active_public)
        self._publics: dict[str, bytes] = {self._active_id: self._active_public}
        for raw in previous_public or []:
            self._publics.setdefault(key_id_of(raw), raw)

    @property
    def active_key_id(self) -> str:
        return self._active_id

    @classmethod
    def generate(cls, previous_public: list[bytes] | None = None) -> "Keyring":
        return cls(Ed25519PrivateKey.generate(), previous_public)

    @classmethod
    def from_private_text(cls, private_b64: str, previous_public: list[bytes] | None = None) -> "Keyring":
        return cls(Ed25519PrivateKey.from_private_bytes(decode_key(private_b64)), previous_public)

    def public_keys(self) -> list[PublicKeyInfo]:
        """The active key first, then the earlier ones. No secret."""
        infos = [
            PublicKeyInfo(kid, ALG, base64.b64encode(raw).decode(), kid == self._active_id)
            for kid, raw in self._publics.items()
        ]
        return sorted(infos, key=lambda i: (not i.active, i.key_id))

    def public_map(self) -> dict[str, bytes]:
        """`key_id` to the 32 raw public key bytes, for `verify_receipt`."""
        return dict(self._publics)

    def public_raw(self, key_id: str) -> bytes | None:
        return self._publics.get(key_id)

    def sign(self, canonical: str) -> tuple[str, str]:
        """`(signature_b64, key_id)` over the UTF-8 bytes of `canonical`."""
        return base64.b64encode(self._active.sign(canonical.encode("utf-8"))).decode(), self._active_id


def keyring_from_settings(settings: Any) -> Keyring:
    """The keyring the settings describe. Local mode with no key makes a throwaway one and logs only its `key_id`."""
    previous = [decode_key(k) for k in settings.previous_receipt_keys]
    if settings.signing_key_text:
        keyring = Keyring.from_private_text(settings.signing_key_text, previous)
        logger.info("receipt signing key loaded: key_id=%s", keyring.active_key_id)
        return keyring
    if settings.mode != "local":
        raise ValueError(f"RECEIPT_SIGNING_KEY must be set when MODE={settings.mode}")
    keyring = Keyring.generate(previous)
    logger.info("receipt signing key generated for local use (not stored): key_id=%s", keyring.active_key_id)
    return keyring


def checkpoint_text(tenant_id: Any, position: int, row_hash: str, reason: str) -> str:
    """The text a chain checkpoint signature covers: tenant, position, hash and reason."""
    return canonical_json({"tenant_id": str(tenant_id), "position": int(position), "row_hash": row_hash, "reason": reason})


def verify_checkpoints(
    tenant_id: Any, checkpoints: list[Mapping[str, Any]], public_keys: Mapping[str, bytes],
) -> Check:
    """Every purge checkpoint must carry a valid signature of the receipt key. A genesis checkpoint (position 0) is
    derived from the tenant id and is not signed. An unsigned, badly signed or unknown-key checkpoint fails."""
    problems: list[str] = []
    for cp in checkpoints:
        position = int(cp["position"])
        if cp.get("reason") == "genesis":
            continue
        raw = public_keys.get(str(cp.get("key_id")))
        if not cp.get("signature") or raw is None:
            problems.append(f"checkpoint {position} is unsigned or signed with an unknown key")
            continue
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(
                base64.b64decode(str(cp["signature"]), validate=True),
                checkpoint_text(tenant_id, position, str(cp["row_hash"]), "purge").encode("utf-8"),
            )
        except (InvalidSignature, binascii.Error, ValueError):
            problems.append(f"checkpoint {position} has a bad signature")
    return Check("checkpoints", not problems, "; ".join(problems) or "every purge checkpoint is signed")


def signed_text(record: Mapping[str, Any], chain: Mapping[str, Any]) -> str:
    return canonical_json({"chain": {"prev_hash": chain["prev_hash"], "row_hash": chain["row_hash"], "position": chain["position"]},
                           "decision": record})


def sign_receipt(keyring: Keyring, record: Mapping[str, Any], chain: Mapping[str, Any]) -> dict[str, str]:
    """The signature part of a receipt: `canonical`, `signature`, `key_id`, `alg`."""
    canonical = signed_text(record, chain)
    signature, key_id = keyring.sign(canonical)
    return {"canonical": canonical, "signature": signature, "key_id": key_id, "alg": ALG}


def record_of(decision: Mapping[str, Any]) -> dict[str, Any]:
    """The decision record rebuilt from a receipt's `decision` object (the console's decision detail)."""
    principal = decision.get("principal")
    tenant = decision.get("tenant") or {}
    return decision_record(
        id=decision["id"], tenant_id=tenant["id"], principal_id=(principal or {}).get("id"),
        request_id=decision["request_id"], action=decision["action"], resource=decision.get("resource"),
        outcome=decision["outcome"], stage=decision["stage"], reason=decision["reason"],
        policy_version=decision.get("policy_version"), input_sha256=decision.get("input_sha256"),
        execution_id=decision.get("execution_id"), created_at=decision["created_at"],
    )


def verify_receipt(receipt: Mapping[str, Any], public_keys: Mapping[str, bytes]) -> list[Check]:
    """Run the receipt checks. Any malformed field is a failed check, never an exception.

    1. `alg`: the algorithm is Ed25519.
    2. `key`: the `key_id` is one of the known public keys.
    3. `canonical`: the signed text is the one the decision and chain fields give (so a changed field is seen).
    4. `signature`: the signature is valid over the signed text.
    5. `row_hash`: the chain hash is the hash of the decision record and the previous hash.
    """
    checks: list[Check] = []
    try:
        decision = receipt["decision"]
        chain = receipt["chain"]
        record = record_of(decision)
        rebuilt = signed_text(record, chain)
        prev_hash, row_hash = str(chain["prev_hash"]), str(chain["row_hash"])
        parsed = True
    except (KeyError, TypeError, ValueError, AttributeError):
        record, rebuilt, prev_hash, row_hash, parsed = {}, "", "", "", False
    alg = receipt.get("alg")
    checks.append(Check("alg", alg == ALG, f"algorithm {alg}" if alg == ALG else f"algorithm {alg!r} is not {ALG}"))
    key_id = str(receipt.get("key_id"))
    raw = public_keys.get(key_id)
    checks.append(Check("key", raw is not None, f"key {key_id} is known" if raw else f"key {key_id} is not a known key"))
    canonical = receipt.get("canonical")
    checks.append(Check(
        "canonical", parsed and canonical == rebuilt,
        "the signed text matches the decision and chain fields" if parsed and canonical == rebuilt
        else "the decision or chain fields do not match the signed text",
    ))
    signature_ok, detail = False, "no key to check against"
    if raw is not None and isinstance(canonical, str):
        try:
            Ed25519PublicKey.from_public_bytes(raw).verify(base64.b64decode(str(receipt.get("signature")), validate=True),
                                                           canonical.encode("utf-8"))
            signature_ok, detail = True, "the signature is valid"
        except (InvalidSignature, binascii.Error, ValueError):
            detail = "the signature does not match the signed text"
    checks.append(Check("signature", signature_ok, detail))
    hash_ok = parsed and compute_row_hash(record, prev_hash) == row_hash
    checks.append(Check(
        "row_hash", hash_ok,
        "the row hash is the hash of the decision and the previous hash" if hash_ok
        else "the row hash does not match the decision and the previous hash",
    ))
    return checks
