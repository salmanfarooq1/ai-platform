import asyncio
import asyncpg
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.settings import get_settings

# Admin-only DDL, so it connects with MIGRATION_DATABASE_URL (the owner role; it falls back to
# DATABASE_URL, and locally to the compose superuser). The app role cannot create indexes and
# must not be able to. The index is already created by migration 0001; this script only rebuilds it
# if it was dropped. It touches no tenant data, so no CORPUS_TENANT_ID is needed.

SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""

async def main():
    conn = await asyncpg.connect(get_settings().migration_dsn)
    try:
        print("Applying HNSW index on documents.embedding ...")
        await conn.execute(SQL)
        print("Done. Verifying ...")
        row = await conn.fetchrow("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename = 'documents' AND indexname = 'idx_documents_embedding_hnsw';
        """)
        if row:
            print(f"Index confirmed: {row['indexname']}")
            print(f"Definition: {row['indexdef']}")
        else:
            print("WARNING: Index not found after creation.")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
