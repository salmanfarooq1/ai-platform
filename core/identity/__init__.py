"""Identity: principals, API keys and token verification. Tenant comes only from a verified credential."""
from core.identity.models import Principal, Scope

__all__ = ["Principal", "Scope"]
