"""Shared fixtures for the integration and e2e tiers (loaded as a pytest plugin from tests/conftest.py).

A fresh database `gap_test_<random>` is created per run, migrated with
`alembic upgrade head`, and dropped at the end. The tier is skipped, with a reason,
when Postgres or Redis is unreachable. LLM and embeddings are the fakes in tests/fakes.py.

Two database URLs matter. `database_url` is the owner (superuser) role: it migrates, truncates and
verifies. `app_database_url` is `gap_app`, a NOSUPERUSER NOBYPASSRLS role, and it is the only role
the app and the operations under test use, so row-level security really applies to them.
"""
from dataclasses import dataclass, field

import pytest

from core.identity.admin import admin_connection, create_kb, create_key, create_principal, create_tenant
from tests import harness
from tests.fakes import FakeEmbeddings, FakeLLM

KB_DESCRIPTIONS = {
    "legal": "GDPR, CCPA, HIPAA, and other data protection regulations",
    "kyc_aml": "KYC, AML, and Bank Secrecy Act documentation",
    "default": "Uncategorized or general compliance documents",
}
KEY_SCOPES = {
    "full": ["kb:read", "kb:write", "query", "agent"],
    "query_only": ["query"],
    "reader": ["kb:read"],
}


@dataclass
class TenantFixture:
    slug: str
    id: str
    principal_id: str
    tokens: dict[str, str] = field(default_factory=dict)
    prefixes: dict[str, str] = field(default_factory=dict)

    def headers(self, key: str = "full") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[key]}"}


def principal_of(tenant: TenantFixture, scopes=("kb:read", "kb:write", "query", "agent")):
    """The Principal the middleware would build for `tenant`'s service principal."""
    from uuid import UUID

    from core.identity.models import Principal

    return Principal(id=UUID(tenant.principal_id), tenant_id=UUID(tenant.id), kind="service", scopes=frozenset(scopes))


@pytest.fixture(scope="session")
def database_url():
    harness.require_postgres()
    harness.ensure_app_role()
    name, dsn = harness.create_database()
    try:
        harness.migrate(dsn)
        yield dsn
    finally:
        harness.drop_database(name)


@pytest.fixture(scope="session")
def app_database_url(database_url):
    return harness.app_url(database_url)


@pytest.fixture
def clean_state(database_url):
    harness.require_redis()
    harness.truncate_tables(database_url)
    harness.clean_redis()
    yield
    harness.clean_redis()


def _make_tenant(dsn: str, slug: str) -> TenantFixture:
    with admin_connection(dsn) as conn:
        tenant_id = create_tenant(conn, slug, default_kb=False, deploy_shape="multi_tenant")
        for kb_slug, description in KB_DESCRIPTIONS.items():
            create_kb(conn, slug, kb_slug, description)
        principal_id = create_principal(conn, slug, "service", f"{slug}-service")
        tenant = TenantFixture(slug=slug, id=str(tenant_id), principal_id=str(principal_id))
        for name, scopes in KEY_SCOPES.items():
            key = create_key(conn, principal_id, scopes)
            tenant.tokens[name] = key.token
            tenant.prefixes[name] = key.prefix
    return tenant


@pytest.fixture
def tenants(database_url, clean_state) -> tuple[TenantFixture, TenantFixture]:
    """Two tenants, A and B. Each owns knowledge bases legal, kyc_aml and default, and has three keys
    (full, query_only, reader) of different scopes."""
    return _make_tenant(database_url, "tenant-a"), _make_tenant(database_url, "tenant-b")


@pytest.fixture
def tenant_a(tenants) -> TenantFixture:
    return tenants[0]


@pytest.fixture
def tenant_b(tenants) -> TenantFixture:
    return tenants[1]


@pytest.fixture
def fake_embeddings():
    """A fake `EmbeddingPort`. A test that asks for it gets the app (and ingestion) built with it."""
    return FakeEmbeddings()


@pytest.fixture
def fake_llm():
    """A fake `LLMPort` and `ChatModelPort`. A test that asks for it gets the app built with it."""
    return FakeLLM()
