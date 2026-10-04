"""Delete one tenant's `legal` knowledge-base content (chunks and registry rows).

Tenant-scoped: runs through tenant_connection for the tenant in CORPUS_TENANT_ID, so it can only ever
touch that tenant's rows. The registry rows go too, otherwise a re-ingest would be skipped as "unchanged".
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _tenant import corpus_tenant_id  # noqa: E402 - the script directory is added to sys.path just above

from core.database.pool import create_pool  # noqa: E402
from core.database.tenant import tenant_connection  # noqa: E402


async def main():
    tenant_id = corpus_tenant_id()
    print(f"Clearing 'legal' namespace for tenant {tenant_id}...")
    pool = await create_pool()
    try:
        async with tenant_connection(pool, tenant_id) as conn:
            chunks = await conn.execute("DELETE FROM documents WHERE tenant_id = $1 AND namespace = 'legal'", tenant_id)
            registry = await conn.execute(
                "DELETE FROM document_registry WHERE tenant_id = $1 AND namespace = 'legal'", tenant_id)
    finally:
        await pool.close()
    print(f"Namespace cleared ({chunks}, {registry}).")

if __name__ == "__main__":
    asyncio.run(main())
