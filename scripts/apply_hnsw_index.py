import asyncio
import asyncpg
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_CONFIG

SQL = """
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""

async def main():
    conn = await asyncpg.connect(DATABASE_CONFIG["url"])
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
