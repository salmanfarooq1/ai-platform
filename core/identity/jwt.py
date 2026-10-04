"""JWT verification (PyJWT). We only verify tokens; we never issue them (no OAuth flows here). The middleware then confirms
the principal and tenant in the database (`store.confirm_jwt_principal`).

Keys come from `JWT_JWKS_URL` (asymmetric) or `JWT_SECRET` (HS256), never both. `exp`, `iss`, `aud`
and `sub` are required. The algorithm allow-list is fixed by the key source, so `alg=none` and
HS/RS confusion are rejected. Claims used: `sub` (the principal's UUID in `principals`), `tenant_id` (UUID), `scope` (space
separated) or `scopes` (list), `principal_kind` (optional, default `user`).
"""
import asyncio
import logging
import uuid
from typing import Any, Protocol

import jwt

from core.identity.models import PRINCIPAL_KINDS, Principal, PrincipalKind, parse_scopes
from core.settings import Settings

logger = logging.getLogger("core.identity.jwt")

_SYMMETRIC_ALGS = ["HS256"]
_ASYMMETRIC_ALGS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256", "PS384", "PS512"]


class JwtError(Exception):
    """The token is not acceptable. The message is for logs, never for the client."""


class SigningKeySource(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class JwtVerifier:
    def __init__(
        self,
        issuer: str,
        audience: str,
        secret: str | None = None,
        key_source: SigningKeySource | None = None,
    ) -> None:
        if (secret is None) == (key_source is None):
            raise ValueError("configure exactly one of secret and key_source")
        self._issuer = issuer
        self._audience = audience
        self._secret = secret
        self._key_source = key_source

    @classmethod
    def from_settings(cls, settings: Settings) -> "JwtVerifier | None":
        if not settings.jwt_enabled:
            return None
        assert settings.jwt_issuer and settings.jwt_audience  # guaranteed by Settings validation
        if settings.jwt_jwks_url:
            return cls(settings.jwt_issuer, settings.jwt_audience, key_source=jwt.PyJWKClient(settings.jwt_jwks_url))
        return cls(settings.jwt_issuer, settings.jwt_audience, secret=settings.jwt_secret)

    def _verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise JwtError("malformed token") from exc
        algorithms = _SYMMETRIC_ALGS if self._secret is not None else _ASYMMETRIC_ALGS
        if header.get("alg") not in algorithms:
            raise JwtError("algorithm not allowed")
        try:
            key: Any = self._secret if self._secret is not None else self._signing_key(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise JwtError(type(exc).__name__) from exc
        return claims

    def _signing_key(self, token: str) -> Any:
        assert self._key_source is not None
        return self._key_source.get_signing_key_from_jwt(token).key

    def principal_from_claims(self, claims: dict[str, Any]) -> Principal:
        try:
            tenant_id = uuid.UUID(str(claims["tenant_id"]))
        except (KeyError, ValueError) as exc:
            raise JwtError("missing or invalid tenant_id claim") from exc
        try:
            principal_id = uuid.UUID(str(claims["sub"]))
        except ValueError as exc:  # `sub` must be the id of a row in `principals`
            raise JwtError("sub is not a principal id") from exc
        raw_scopes = claims.get("scopes")
        if raw_scopes is None:
            raw_scopes = str(claims.get("scope", "")).split()
        if not isinstance(raw_scopes, list):
            raise JwtError("invalid scopes claim")
        kind = claims.get("principal_kind", "user")
        if kind not in PRINCIPAL_KINDS:
            raise JwtError("invalid principal_kind claim")
        typed_kind: PrincipalKind = kind
        return Principal(id=principal_id, tenant_id=tenant_id, kind=typed_kind, scopes=parse_scopes(map(str, raw_scopes)))

    async def verify(self, token: str) -> Principal:
        # The JWKS fetch is blocking network I/O, so verification runs in a worker thread.
        claims = await asyncio.to_thread(self._verify, token)
        return self.principal_from_claims(claims)
