import time
from itertools import islice
from core.ingestion import read_chunks, clean_chunks, embed_chunks
from core.database import create_pool, bulk_insert

def batch_generator(iterable, batch_size : int = 50):
    """
    This function is a generator that yields batches of items from an iterable.
    It is used to batch the chunks for the API requests.
    """
    iterator = iter(iterable) # convert the iterable to an iterator(if so)

    while True:
        sliced_iterator = islice(iterator, batch_size) # slice the iterator to get a an iterator with specific batch that we needed
        batch = list(sliced_iterator) # convert the sliced iterator to a list, so now we have actual chunks
        if not batch: # if batch is empty, break
            break
        yield batch # yield the batch

async def ingestion_pipeline(input_file_path : str, batch_size : int = 50):

    start_time = time.perf_counter() # start the timer, to measure time taken for complete pipeline

    chunks = read_chunks(input_file_path, chunk_size = 1024) # read chunks using read_chunks from readers.py
    cleaned_chunks = clean_chunks(chunks) # clean chunks using clean_chunks from processors.py
    total_chunks = 0
    
    pool = await create_pool()
    for batch in batch_generator(cleaned_chunks, batch_size):
        embedding_tuple_list = list(embed_chunks(batch))
        async with pool.acquire() as conn:
            await bulk_insert(conn, embedding_tuple_list)
        total_chunks += len(embedding_tuple_list)
            
    await pool.close()
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    
    metrics = {
        'total_chunks': total_chunks,
        'total_time_seconds': round(elapsed_time, 3),
        'throughput_chunks_per_second': round(total_chunks / elapsed_time, 2)
    }
    return metrics