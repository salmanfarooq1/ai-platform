"""JWT verification: valid, expired, wrong aud/iss, alg=none, bad signature, algorithm confusion."""
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from core.identity.jwt import JwtError, JwtVerifier

SECRET = "s" * 64
ISSUER = "https://issuer.example.test/"
AUDIENCE = "gap-api"
TENANT = uuid4()
SUBJECT = uuid4()


def claims(**override):
    base = {
        "sub": str(SUBJECT), "tenant_id": str(TENANT), "scope": "query kb:read",
        "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 300,
    }
    base.update(override)
    return {k: v for k, v in base.items() if v is not None}


def hs_token(payload=None, secret=SECRET, alg="HS256"):
    return jwt.encode(payload if payload is not None else claims(), secret, algorithm=alg)


@pytest.fixture
def verifier():
    return JwtVerifier(ISSUER, AUDIENCE, secret=SECRET)


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def rs_verifier(rsa_key):
    source = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=rsa_key.public_key()))
    return JwtVerifier(ISSUER, AUDIENCE, key_source=source)


async def test_valid_token_gives_a_principal_from_its_claims(verifier):
    principal = await verifier.verify(hs_token())
    assert principal.id == SUBJECT
    assert principal.tenant_id == TENANT
    assert principal.kind == "user"
    assert principal.scopes == frozenset({"query", "kb:read"})


async def test_scopes_list_claim_and_principal_kind_are_read(verifier):
    principal = await verifier.verify(hs_token(claims(scope=None, scopes=["agent", "admin"], principal_kind="agent")))
    assert principal.scopes == frozenset({"agent", "admin"})
    assert principal.kind == "agent"


async def test_unknown_scopes_grant_nothing(verifier):
    principal = await verifier.verify(hs_token(claims(scope="query superuser kb:delete")))
    assert principal.scopes == frozenset({"query"})


async def test_a_subject_that_is_not_a_principal_uuid_is_rejected(verifier):
    """`sub` must be the id of a row in `principals`; there is no mapping from foreign subjects."""
    with pytest.raises(JwtError, match="sub is not a principal id"):
        await verifier.verify(hs_token(claims(sub="auth0|abc123")))


@pytest.mark.parametrize("payload, why", [
    (claims(exp=int(time.time()) - 10), "expired"),
    (claims(aud="someone-else"), "wrong audience"),
    (claims(iss="https://evil.example.test/"), "wrong issuer"),
    (claims(exp=None), "no exp"),
    (claims(aud=None), "no aud"),
    (claims(iss=None), "no iss"),
    (claims(sub=None), "no sub"),
    (claims(tenant_id=None), "no tenant"),
    (claims(tenant_id="not-a-uuid"), "bad tenant"),
    (claims(principal_kind="root"), "bad kind"),
    (claims(scope=None, scopes="query"), "scopes must be a list"),
    (claims(nbf=int(time.time()) + 600), "not yet valid"),
])
async def test_bad_claims_are_rejected(verifier, payload, why):
    with pytest.raises(JwtError):
        await verifier.verify(hs_token(payload))


async def test_wrong_signature_is_rejected(verifier):
    with pytest.raises(JwtError):
        await verifier.verify(hs_token(secret="x" * 64))


async def test_tampered_payload_is_rejected(verifier):
    header, _, signature = hs_token().split(".")
    forged = base64.urlsafe_b64encode(json.dumps(claims(tenant_id=str(uuid4()))).encode()).rstrip(b"=").decode()
    with pytest.raises(JwtError):
        await verifier.verify(f"{header}.{forged}.{signature}")


async def test_alg_none_is_rejected(verifier):
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims())}."
    with pytest.raises(JwtError, match="algorithm not allowed"):
        await verifier.verify(unsigned)


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "not.a.jwt.at.all"])
async def test_garbage_is_rejected(verifier, token):
    with pytest.raises(JwtError):
        await verifier.verify(token)


async def test_hs384_is_not_in_the_allow_list(verifier):
    with pytest.raises(JwtError, match="algorithm not allowed"):
        await verifier.verify(hs_token(alg="HS384"))


async def test_rsa_token_verifies_against_the_key_source(rsa_key):
    token = jwt.encode(claims(), rsa_key, algorithm="RS256", headers={"kid": "k1"})
    principal = await rs_verifier(rsa_key).verify(token)
    assert principal.tenant_id == TENANT


async def test_rsa_token_signed_by_another_key_is_rejected(rsa_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims(), other, algorithm="RS256")
    with pytest.raises(JwtError):
        await rs_verifier(rsa_key).verify(token)


async def test_hs256_token_signed_with_the_public_key_is_rejected_by_a_jwks_verifier(rsa_key):
    """Algorithm confusion: the public key is not a secret, so an HS256 token made from it must not pass."""
    public_pem = rsa_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    # PyJWT refuses to build this token, so sign it by hand the way an attacker would.
    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    signing_input = f"{b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())}.{b64(json.dumps(claims()).encode())}"
    signature = hmac.new(public_pem.encode(), signing_input.encode(), hashlib.sha256).digest()
    forged = f"{signing_input}.{b64(signature)}"
    with pytest.raises(JwtError, match="algorithm not allowed"):
        await rs_verifier(rsa_key).verify(forged)


async def test_rsa_token_is_rejected_by_a_secret_verifier(verifier, rsa_key):
    token = jwt.encode(claims(), rsa_key, algorithm="RS256")
    with pytest.raises(JwtError, match="algorithm not allowed"):
        await verifier.verify(token)


def test_verifier_needs_exactly_one_key_source():
    with pytest.raises(ValueError):
        JwtVerifier(ISSUER, AUDIENCE)
    with pytest.raises(ValueError):
        JwtVerifier(ISSUER, AUDIENCE, secret=SECRET, key_source=SimpleNamespace())


def test_error_messages_never_contain_the_token(verifier):
    token = hs_token(secret="x" * 64)
    with pytest.raises(JwtError) as exc:
        verifier._verify(token)
    assert token not in str(exc.value)
    assert "x" * 64 not in str(exc.value)
