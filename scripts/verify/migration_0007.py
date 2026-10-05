"""Show migration 0007 on data from 0005 (Sprint 006, acceptance A5): counts before and after, and the backfill.

    poetry run python scripts/verify/migration_0007.py

Creates a throwaway database, migrates to 0005, seeds two tenants with chunks and decisions, upgrades to head, prints
what changed, and drops the database. Needs Postgres (`docker compose up -d postgres`).
"""
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tests import harness  # noqa: E402 - needs the sys.path line above. It imports no app config.


def query(dsn: str, sql: str):
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def main() -> int:
    from core.settings import get_settings
    from tests.integration.test_migration_0007 import seed_0005

    harness.require_postgres()
    name, dsn = harness.create_database("gap_mig7v_")
    try:
        harness.migrate(dsn, "0005")
        seed_0005(dsn)
        print("before (revision 0005):")
        print("  documents:", query(dsn, "SELECT count(*) FROM documents")[0][0],
              "| per tenant:", query(dsn, "SELECT t.slug, count(*) FROM documents d JOIN tenants t ON t.id = d.tenant_id GROUP BY 1 ORDER BY 1"))
        print("  gateway_decisions:", query(dsn, "SELECT count(*) FROM gateway_decisions")[0][0])
        print("  documents has embedding_model:", bool(query(
            dsn, "SELECT 1 FROM information_schema.columns WHERE table_name = 'documents' AND column_name = 'embedding_model'")))
        harness.migrate(dsn)
        settings = get_settings()
        print(f"after (revision {query(dsn, 'SELECT version_num FROM alembic_version')[0][0]}), configured model {settings.embed_model!r} dim {settings.embedding_dim}:")
        print("  documents:", query(dsn, "SELECT count(*) FROM documents")[0][0],
              "| per tenant:", query(dsn, "SELECT t.slug, count(*) FROM documents d JOIN tenants t ON t.id = d.tenant_id GROUP BY 1 ORDER BY 1"))
        print("  gateway_decisions:", query(dsn, "SELECT count(*) FROM gateway_decisions")[0][0])
        print("  distinct (embedding_model, embedding_dim):", query(dsn, "SELECT DISTINCT embedding_model, embedding_dim FROM documents"))
        print("  rows without a model or dimension:", query(dsn, "SELECT count(*) FROM documents WHERE embedding_model IS NULL OR embedding_dim IS NULL")[0][0])
        print("  not null:", query(dsn, "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'documents' "
                                      "AND column_name IN ('embedding_model', 'embedding_dim') ORDER BY 1"))
        print("  gateway_decisions.execution_id:", query(dsn, "SELECT data_type, is_nullable FROM information_schema.columns "
                                                        "WHERE table_name = 'gateway_decisions' AND column_name = 'execution_id'"))
        print("  indexes:", [r[0] for r in query(dsn, "SELECT indexname FROM pg_indexes WHERE indexname IN "
                                                    "('idx_documents_embedding_provenance', 'idx_gateway_decisions_execution') ORDER BY 1")])
        print("  count_stale_vectors(configured model):", query(dsn, f"SELECT count_stale_vectors('{settings.embed_model}', {settings.embedding_dim})")[0][0])
        print("  count_stale_vectors('other/model'):", query(dsn, f"SELECT count_stale_vectors('other/model', {settings.embedding_dim})")[0][0])
    finally:
        harness.drop_database(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
