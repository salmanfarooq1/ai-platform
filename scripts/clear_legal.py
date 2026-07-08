import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database.pool import create_pool

async def main():
    print("Clearing 'legal' namespace...")
    pool = await create_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM documents WHERE namespace = 'legal'")
    await pool.close()
    print("Namespace cleared.")

if __name__ == "__main__":
    asyncio.run(main())
