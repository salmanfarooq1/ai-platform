import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database.pool import create_pool

async def main():
    pool = await create_pool()
    
    # Namespace counts
    rows = await pool.fetch(
        "SELECT namespace, COUNT(*) as cnt FROM documents GROUP BY namespace ORDER BY namespace"
    )
    print("=== Namespaces in DB ===")
    for r in rows:
        print(f"  {r['namespace']}: {r['cnt']} chunks")
    
    # Verify fts_vector column and GIN index exist
    has_fts = await pool.fetchval(
        "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='documents' AND column_name='fts_vector'"
    )
    print(f"\n=== fts_vector column exists: {bool(has_fts)} ===")
    
    # Verify GIN index
    idx = await pool.fetchrow(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='documents' AND indexname='idx_documents_fts'"
    )
    print(f"GIN index idx_documents_fts: {'EXISTS' if idx else 'MISSING'}")
    
    # Verify HNSW vector index
    vidx = await pool.fetchrow(
        "SELECT indexname FROM pg_indexes WHERE tablename='documents' AND indexname LIKE '%embedding%'"
    )
    print(f"Vector (HNSW) index: {'EXISTS → ' + vidx['indexname'] if vidx else 'MISSING'}")
    
    # Check fts_vector null count in legal namespace
    null_fts = await pool.fetchval(
        "SELECT COUNT(*) FROM documents WHERE namespace='legal' AND fts_vector IS NULL"
    )
    print(f"\n=== legal namespace: fts_vector NULLs = {null_fts} (should be 0) ===")
    
    # Sample a metadata cell to verify it's a JSON string (not dict)
    sample = await pool.fetchrow(
        "SELECT pg_typeof(metadata) as typ, metadata FROM documents WHERE namespace='legal' LIMIT 1"
    )
    if sample:
        raw = sample['metadata']
        print(f"\n=== Sample metadata from DB ===")
        print(f"  pg_typeof: {sample['typ']}")
        print(f"  Python type: {type(raw).__name__}")
        print(f"  First 100 chars: {str(raw)[:100]}")
    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
