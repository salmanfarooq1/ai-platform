"""API key format, generation, hashing and constant-time verification.

Format: `gap_<8-char prefix>_<secret>`. The prefix is public and indexes the lookup; the secret is
random (256 bits) and only its SHA-256 hash is stored. SHA-256 is enough because the secret is
high-entropy random data, not a human password. The plaintext exists once, at creation.
"""
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

KEY_PREFIX_TAG = "gap"
PREFIX_LENGTH = 8
_PREFIX_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_KEY_RE = re.compile(rf"{KEY_PREFIX_TAG}_([a-z0-9]{{{PREFIX_LENGTH}}})_([A-Za-z0-9_-]{{32,128}})")

# Hash compared against when the prefix is unknown, so unknown and wrong-secret take the same path.
DUMMY_HASH = hashlib.sha256(b"no-such-key").hexdigest()


@dataclass(frozen=True)
class GeneratedKey:
    prefix: str
    token: str  # the full key. Show it once, never store or log it.
    secret_hash: str


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_key() -> GeneratedKey:
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(PREFIX_LENGTH))
    secret = secrets.token_urlsafe(32)
    return GeneratedKey(prefix=prefix, token=f"{KEY_PREFIX_TAG}_{prefix}_{secret}", secret_hash=hash_secret(secret))


def parse_key(token: str) -> tuple[str, str] | None:
    """Split a token into (prefix, secret), or None if it is not in key format."""
    match = _KEY_RE.fullmatch(token)  # fullmatch: a `$` anchor would accept a trailing newline
    if match is None:
        return None
    return match.group(1), match.group(2)


def verify_secret(secret: str, stored_hash: str) -> bool:
    """Constant-time comparison of the hash of `secret` with the stored hash."""
    return hmac.compare_digest(hash_secret(secret).encode("ascii"), stored_hash.encode("ascii", errors="replace"))
