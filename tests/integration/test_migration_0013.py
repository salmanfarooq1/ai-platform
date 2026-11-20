"""Migration 0013 (hosted-deploy fix): bare hosted embedding labels gain the runtime `@provider_model_id` suffix."""
import importlib.util
from pathlib import Path

import pytest

from tests import harness
from tests.integration.test_migration_0007 import VECTOR_SQL, _exec

pytestmark = pytest.mark.integration
MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0013_hosted_embedding_provenance.py"

LABELS = {
    "hosted-bare.md": ("gemini/gemini-embedding-001", "gemini/gemini-embedding-001@gemini-embedding-001"),
    "hosted-done.md": ("gemini/gemini-embedding-001@gemini-embedding-001", "gemini/gemini-embedding-001@gemini-embedding-001"),
    "local-bare.md": ("ollama/nomic-embed-text", "ollama/nomic-embed-text"),
    "local-done.md": ("ollama/nomic-embed-text@sha256:abc", "ollama/nomic-embed-text@sha256:abc"),
}


@pytest.fixture
def blank_db():
    harness.require_postgres()
    name, dsn = harness.create_database(prefix="gap_mig13_")
    try:
        yield dsn
    finally:
        harness.drop_database(name)


def test_only_bare_hosted_labels_are_relabelled_and_a_rerun_changes_nothing(blank_db):
    harness.migrate(blank_db, "0012")
    tenant = _exec(blank_db, "SELECT id FROM tenants ORDER BY created_at LIMIT 1")[0][0]
    for document_id, (before, _) in LABELS.items():
        _exec(blank_db, "INSERT INTO documents (tenant_id, document_id, namespace, content, embedding, embedding_model, "
                        f"embedding_dim) VALUES (%s, %s, 'legal', 'chunk', {VECTOR_SQL}, %s, 768)",
              (tenant, document_id, before))
    harness.migrate(blank_db)
    assert _exec(blank_db, "SELECT version_num FROM alembic_version") == [("0013",)]
    expected = sorted((document_id, after) for document_id, (_, after) in LABELS.items())
    assert _exec(blank_db, "SELECT document_id, embedding_model FROM documents ORDER BY document_id") == expected
    _exec(blank_db, _relabel_sql())
    assert _exec(blank_db, "SELECT document_id, embedding_model FROM documents ORDER BY document_id") == expected


def _relabel_sql() -> str:
    spec = importlib.util.spec_from_file_location("m0013", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RELABEL
