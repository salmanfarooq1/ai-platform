"""API key format, hashing and constant-time verification (requirement 5, 9)."""
import hashlib
import hmac
import re

import pytest

from core.identity import keys
from core.identity.keys import generate_key, hash_secret, parse_key, verify_secret


def test_generated_key_has_the_documented_format():
    key = generate_key()
    assert re.fullmatch(r"gap_[a-z0-9]{8}_[A-Za-z0-9_-]{43}", key.token)
    assert key.prefix == key.token.split("_")[1]
    assert len(key.prefix) == 8


def test_generated_keys_are_unique_and_high_entropy():
    tokens = {generate_key().token for _ in range(200)}
    assert len(tokens) == 200
    assert len({generate_key().prefix for _ in range(200)}) > 190  # 36^8 prefixes: collisions are vanishingly rare


def test_stored_hash_is_sha256_of_the_secret_only_and_never_contains_the_token():
    key = generate_key()
    secret = parse_key(key.token)[1]
    assert key.secret_hash == hashlib.sha256(secret.encode()).hexdigest()
    assert hash_secret(secret) == key.secret_hash
    assert secret not in key.secret_hash and key.token not in key.secret_hash
    assert len(key.secret_hash) == 64


def test_parse_key_returns_prefix_and_secret_even_when_the_secret_contains_underscores():
    prefix, secret = parse_key("gap_abcd1234_" + "a_b-" * 10)
    assert prefix == "abcd1234"
    assert secret == "a_b-" * 10


@pytest.mark.parametrize("token", [
    "",
    "gap_",
    "gap_abcd1234",
    "gap_abcd1234_short",                       # secret under 32 chars
    "xyz_abcd1234_" + "a" * 43,                 # wrong tag
    "gap_ABCD1234_" + "a" * 43,                 # prefix must be lowercase alphanumeric
    "gap_abcd123_" + "a" * 43,                  # prefix too short
    "gap_abcd12345_" + "a" * 43,                # prefix too long
    "gap_abcd1234_" + "a" * 43 + "!",           # illegal character
    "gap_abcd1234_" + "a" * 43 + "\n",          # trailing newline must not slip through `$`
    "Bearer gap_abcd1234_" + "a" * 43,
    "eyJhbGciOiJIUzI1NiJ9.e30.sig",
])
def test_parse_key_rejects_anything_not_in_key_format(token):
    assert parse_key(token) is None


def test_verify_secret_accepts_the_right_secret_and_rejects_others():
    key = generate_key()
    secret = parse_key(key.token)[1]
    assert verify_secret(secret, key.secret_hash) is True
    assert verify_secret(secret + "x", key.secret_hash) is False
    assert verify_secret("", key.secret_hash) is False
    assert verify_secret(secret, "0" * 64) is False


def test_verify_secret_does_not_crash_on_a_non_ascii_stored_hash():
    assert verify_secret("a" * 43, "é" * 64) is False


def test_verification_uses_constant_time_comparison(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(keys.hmac, "compare_digest", spy)
    key = generate_key()
    verify_secret(parse_key(key.token)[1], key.secret_hash)
    assert len(calls) == 1
    assert calls[0][1] == key.secret_hash.encode()
