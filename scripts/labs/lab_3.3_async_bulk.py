import asyncpg
import random
import time
from pgvector.asyncpg import register_vector
import numpy as np


NUM_ROWS = 10000
embeddings_list = np.array([[random.random() for _ in range(128)] for _ in range(NUM_ROWS)])

# await conn.execute() outside the async functions will not work

async def get_connection():
    conn = await asyncpg.connect(host = 'localhost', port = 5432, database = 'postgres', user = 'postgres', password = 'postgres')
    await register_vector(conn)
    return conn

async def setup():
    conn = await get_connection()

    await conn.execute('CREATE EXTENSION IF NOT EXISTS vector') 
    
    await conn.execute('DROP TABLE IF EXISTS embeddings_table') # drop table for clean benchmarks
    await conn.execute('CREATE TABLE embeddings_table(id SERIAL PRIMARY KEY, embedding vector(128))') 
    await conn.close()

async def seq():
    start = time.perf_counter()
    conn = await get_connection()

    # sequential inserts, even in async code, this will be slow

    for emb in embeddings_list:
        await conn.execute('INSERT INTO embeddings_table (embedding) VALUES ($1) ', emb)

    await conn.close() # better to close, prevents leaks 
    end = time.perf_counter()
    seq_time = end - start
    print(f'Seq time: {round(seq_time, 2)}')

    return seq_time 

async def copy():
    start = time.perf_counter()
    conn = await get_connection()

    data = [(emb,) for emb in embeddings_list]

    # copy_records_to_table is much faster than sequential inserts
    # it uses the COPY command which is much more efficient
    

    await conn.copy_records_to_table(
        'embeddings_table',
        records = data,
        columns = ['embedding']
    )

    await conn.close()
    end = time.perf_counter()
    copy_time = end - start
    print(f'Copy time: {round(copy_time, 2)}')

    return copy_time

import json
from pathlib import Path

def save_benchmarks(seq_time, copy_time, filename="lab_3.3_asyncpg_benchmarks.json"):
    """Save benchmark results to JSON."""
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
    benchmarks_dir.mkdir(exist_ok=True)
    
    results = {
        'num_rows': NUM_ROWS,
        'embedding_dimensions': 128,
        'library': 'asyncpg',
        'approaches': [
            {
                'name': 'row_by_row_asyncpg',
                'time_s': round(seq_time, 3),
                'throughput_rows_per_s': round(NUM_ROWS / seq_time, 2)
            },
            {
                'name': 'copy_asyncpg',
                'time_s': round(copy_time, 3),
                'throughput_rows_per_s': round(NUM_ROWS / copy_time, 2),
                'speedup': str(round(seq_time / copy_time, 2)) + 'x'
            }
        ]
    }
    
    filepath = benchmarks_dir / filename
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Benchmarks saved to: {filepath}")

async def main():
    await setup()
    seq_time = await seq()
    copy_time = await copy()
    print(f'Seq rows per second: {round(NUM_ROWS / seq_time, 2)}')
    print(f'Copy rows per second: {round(NUM_ROWS / copy_time, 2)}')
    print(f'Speedup: {round(seq_time / copy_time, 2)}x')

    save_benchmarks(seq_time, copy_time)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
