import psycopg2
import random
import time
from psycopg2.extras import execute_batch

NUM_ROWS = 10000 # number of rows for fake embeddings storing in a list in memory

# Generate fake embeddings
embeddings_list = [[random.random() for _ in range(128)] for _ in range(NUM_ROWS)]

#create a function so simple to use anywhere

def get_connection():
    return psycopg2.connect(
        host='localhost',
        port=5432,
        database='postgres',
        user='postgres',
        password='postgres'
    )

# Setup: Create table
def setup_table():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('DROP TABLE IF EXISTS embeddings') #why: it is safe, idempotent
    cursor.execute('''
        CREATE TABLE embeddings (
            id SERIAL PRIMARY KEY,
            embedding FLOAT[]
        )
    ''') # FLOAT[] is a built in postgres type that contains floats list, we do not use vector(128) here because we are not using pgvector yet, will do that in next lab
    
    conn.commit()
    cursor.close()
    conn.close() # prevents any leaks
    print("Table created")

# Test 1: Row-by-row 
def test_naive():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Clear table
    cursor.execute('TRUNCATE embeddings')
    conn.commit()
    
    start = time.perf_counter()
    
    # Insert one by one, loop through list, n of rows = n of transactions
    for emb in embeddings_list:
        cursor.execute(
            'INSERT INTO embeddings (embedding) VALUES (%s)',
            (emb,)  # Tuple with one element (the embedding list)
        )
    
    conn.commit()
    total_time = time.perf_counter() - start
    
    cursor.close()
    conn.close()
    
    return total_time

# Test 2: executemany (fake bulk)
def test_executemany():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('TRUNCATE embeddings')
    conn.commit()
    
    start = time.perf_counter()
    
    # Prepare data as list of tuples
    data = [(emb,) for emb in embeddings_list]
    
    # executemany just loops execute() internally, SAME AS ABOVE
    cursor.executemany(
        'INSERT INTO embeddings (embedding) VALUES (%s)',
        data
    )
    
    conn.commit()
    total_time = time.perf_counter() - start
    
    cursor.close()
    conn.close()
    
    return total_time

# Test 3: execute_batch, actually bulk loading happens here
def test_execute_batch(page_size=1000):
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('TRUNCATE embeddings')
    conn.commit()
    
    start = time.perf_counter()
    
    # Prepare data as list of tuples, why: execute_batch expects list of tuples
    data = [(emb,) for emb in embeddings_list]
    
    # actual bulk insert happens here, data goes in batches
    execute_batch(
        cursor,
        'INSERT INTO embeddings (embedding) VALUES (%s)',
        data,
        page_size=page_size
    )
    
    conn.commit()
    total_time = time.perf_counter() - start
    
    cursor.close()
    conn.close()
    
    return total_time

def save_benchmarks(time1, time2, time3, filename="lab_3.2_psycopg2_benchmarks.json"):
    """Save Lab 3.2 benchmark results to JSON."""
    import json
    from pathlib import Path
    
    benchmarks_dir = Path(__file__).parent.parent / "benchmarks"
    benchmarks_dir.mkdir(exist_ok=True)
    
    results = {
        'num_rows': NUM_ROWS,
        'embedding_dimensions': 128,
        'library': 'psycopg2',
        'approaches': [
            {
                'name': 'row_by_row',
                'time_s': round(time1, 3),
                'throughput_rows_per_s': round(NUM_ROWS / time1, 2)
            },
            {
                'name': 'executemany',
                'time_s': round(time2, 3),
                'throughput_rows_per_s': round(NUM_ROWS / time2, 2),
                'speedup_vs_row_by_row': str(round(time1 / time2, 2)) + 'x'
            },
            {
                'name': 'execute_batch',
                'time_s': round(time3, 3),
                'throughput_rows_per_s': round(NUM_ROWS / time3, 2),
                'speedup_vs_row_by_row': str(round(time1 / time3, 2)) + 'x'
            }
        ]
    }
    
    filepath = benchmarks_dir / filename
    with open(filepath, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Benchmarks saved to: {filepath}")
    return results


# Run tests
def main():
    setup_table()
    
    print(f"\n{'-'*60}")
    print(f"Lab 3.2: Bulk vs Row-by-Row ({NUM_ROWS} rows)")
    print(f"{'-'*60}")
    
    # Test 1
    print(f"\nTest 1: Row-by-row...")
    time1 = test_naive()
    print(f"   Time: {time1:.3f}s")
    print(f"   Throughput: {NUM_ROWS/time1:.2f} rows/s")
    
    # Test 2
    print(f"\nTest 2: executemany...")
    time2 = test_executemany()
    print(f"   Time: {time2:.3f}s")
    print(f"   Throughput: {NUM_ROWS/time2:.2f} rows/s")
    print(f"   Speedup: {time1/time2:.2f}x")
    
    # Test 3
    print(f"\nTest 3: execute_batch...")
    time3 = test_execute_batch(page_size=100)
    print(f"   Time: {time3:.3f}s")
    print(f"   Throughput: {NUM_ROWS/time3:.2f} rows/s")
    print(f"   Speedup: {time1/time3:.2f}x")

    save_benchmarks(time1, time2, time3)

if __name__ == "__main__":
    main()