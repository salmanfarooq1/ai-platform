"""Typed identity models. A Principal is immutable and is built only from a verified credential."""
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
from uuid import UUID

PrincipalKind = Literal["user", "service", "agent"]
PRINCIPAL_KINDS: tuple[str, ...] = ("user", "service", "agent")


class Scope(str, Enum):
    """Coarse authorization scopes. `admin` satisfies every other scope."""

    KB_READ = "kb:read"
    KB_WRITE = "kb:write"
    QUERY = "query"
    AGENT = "agent"
    AUDIT_READ = "audit:read"
    ADMIN = "admin"


ALL_SCOPES: frozenset[str] = frozenset(s.value for s in Scope)


def parse_scopes(values: Iterable[str]) -> frozenset[str]:
    """Keep only known scopes. An unknown scope grants nothing."""
    return frozenset(v for v in values if v in ALL_SCOPES)


@dataclass(frozen=True)
class Principal:
    id: UUID
    tenant_id: UUID
    kind: PrincipalKind
    scopes: frozenset[str]
    # The API key this principal was authenticated with, when it was one. A run token minted for the principal ends when
    # that key is revoked (Sprint 009 QA L6). Not part of identity: two principals are equal by id, tenant, kind and scopes.
    credential_id: UUID | None = field(default=None, compare=False)

    def has_scope(self, scope: Scope | str) -> bool:
        needed = scope.value if isinstance(scope, Scope) else scope
        return needed in self.scopes or Scope.ADMIN.value in self.scopes
