import asyncpg
import random
import time
import asyncio
from pgvector.asyncpg import register_vector
import json
from pathlib import Path

def create_batches(embeddings, batch_size):
    for i in range(0, len(embeddings), batch_size):
        yield embeddings[i:i + batch_size]

async def setup():
    conn = await asyncpg.connect(
        host = 'localhost',
        port = 5432,
        database = 'postgres',
        user = 'postgres',
        password = 'postgres',
    )
    await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
    await conn.execute('DROP TABLE IF EXISTS embeddings_table')
    await conn.execute('CREATE TABLE embeddings_table(id SERIAL PRIMARY KEY, embedding vector(768))')
    await conn.close()

async def test_no_pool(embeddings, batch_size):
    setup_conn = await asyncpg.connect(
        host='localhost', port=5432,
        database='postgres', user='postgres', password='postgres'
    )
    await setup_conn.execute('TRUNCATE TABLE embeddings_table')
    await setup_conn.close()

    start = time.perf_counter()
    batches = create_batches(embeddings, batch_size)
    for batch in batches:
        conn = await asyncpg.connect(
            host='localhost', port=5432,
            database='postgres', user='postgres', password='postgres'
        )

        await register_vector(conn)
        records = [(embedding,) for embedding in batch]


        await conn.copy_records_to_table(
            'embeddings_table',
            records=records,
            columns=['embedding']
        )
        await conn.close()

    end = time.perf_counter()
    time_elapsed = end - start
    print(f"No pool:        {time_elapsed:.3f}s")
    return time_elapsed

async def test_pool_sequential(embeddings, batch_size, pool):
    async with pool.acquire() as conn:
        await conn.execute('TRUNCATE TABLE embeddings_table')

    start = time.perf_counter()
    batches = create_batches(embeddings, batch_size)
    for batch in batches:
        records = [(embedding,) for embedding in batch]
        async with pool.acquire() as conn:
            await conn.copy_records_to_table(
                'embeddings_table',
                records=records,
                columns=['embedding']
            )

    end = time.perf_counter()
    time_elapsed = end - start
    print(f"Pool sequential: {time_elapsed:.3f}s")
    return time_elapsed

async def test_pool_concurrent(embeddings, batch_size, pool):
    async with pool.acquire() as conn:
        await conn.execute('TRUNCATE TABLE embeddings_table')

    start = time.perf_counter()
    batches = create_batches(embeddings, batch_size)
    async def insert_batches(batch):
        records = [(embedding,) for embedding in batch]
        async with pool.acquire() as conn:
            await conn.copy_records_to_table(
                    'embeddings_table',
                    records=records,
                    columns=['embedding']
                )
    tasks = [insert_batches(batch) for batch in batches]
    await asyncio.gather(*tasks)
    end = time.perf_counter()
    time_elapsed = end - start
    print(f"Pool concurrent: {time_elapsed:.3f}s")
    return time_elapsed
async def main():

    NUM_ROWS = 10000
    BATCH_SIZE = 1000
    embeddings_list = [[random.random() for _ in range(768)] for _ in range(NUM_ROWS)]

    pool = await asyncpg.create_pool(
        host = 'localhost',
        port = 5432,
        database = 'postgres',
        user = 'postgres',
        password = 'postgres',
        min_size = 2,
        max_size = 10,
        init = register_vector
    )
    await setup()
    no_pool_time = await test_no_pool(embeddings_list, BATCH_SIZE)
    pool_sequential_time = await test_pool_sequential(embeddings_list, BATCH_SIZE, pool)
    pool_concurrent_time = await test_pool_concurrent(embeddings_list, BATCH_SIZE, pool)
    await pool.close()
    
    print(f"No pool: {no_pool_time:.3f}sec")
    print(f"Pool sequential: {pool_sequential_time:.3f}sec")
    print(f"Pool concurrent: {pool_concurrent_time:.3f}sec")

    results = {
        "no_pool": f"{round(no_pool_time, 3)}sec",
        "pool_sequential": f"{round(pool_sequential_time, 3)}sec",
        "pool_concurrent": f"{round(pool_concurrent_time, 3)}sec"
    }

    output_path = Path(__file__).parent.parent / "benchmarks" / "lab_3_4_results.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Benchmarks saved to {output_path}")

if __name__ == '__main__':
    asyncio.run(main())
    

