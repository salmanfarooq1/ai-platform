#resolve path issue

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


import asyncio
import asyncpg
from core.pipeline.db_ingest import ingestion_pipeline

async def main():
    # run the pipeline
    metrics = await ingestion_pipeline('scripts/test_data/1mb_test.txt')
    print("\n--- Pipeline Metrics ---")
    print(f"Total chunks:  {metrics['total_chunks']}")
    print(f"Total time:    {metrics['total_time_seconds']}s")
    print(f"Throughput:    {metrics['throughput_chunks_per_second']} chunks/sec")

    # verify rows in db
    conn = await asyncpg.connect(
        host='localhost', port=5432,
        database='postgres', user='postgres', password='postgres'
    )
    count = await conn.fetchval('SELECT COUNT(*) FROM documents')
    await conn.close()

    print(f"\n--- DB Verification ---")
    print(f"Rows in database: {count}")
    print(f"Match: {count == metrics['total_chunks']}")

asyncio.run(main())