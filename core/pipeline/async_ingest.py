import asyncio
import time
import json
import aiohttp
from itertools import islice
from core.clients.async_http_client import AsyncHttpClient
from core.ingestion.readers import read_chunks
from core.ingestion.processors import clean_chunks

# define the main pipeline in async

async def ingestion_pipeline(api_url : str, input_file_path : str, batch_size : int = 50, max_concurrent : int = 25, output_file_path: str = "",api_key: str = "") -> dict:

    start_time = time.perf_counter() # start the timer, to measure time taken for complete pipeline

    chunks = read_chunks(input_file_path, chunk_size = 1024) # read chunks using read_chunks from readers.py
    cleaned_chunks = clean_chunks(chunks) # clean chunks using clean_chunks from processors.py
    
    # initialize variables to keep track of total chunks and successful chunks
    total_chunks = 0 
    successful_chunks = 0

    # prepare headers for the API request, authorization is optional because it is mock for now, if we use real API key, then we will set the auth as well
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    # create async http client, that we already built in lab 2.4, imported it from core/clients module
    # this client will handle the concurrent requests
    async with AsyncHttpClient(max_concurrent=max_concurrent, timeout = 30) as client:
        for batch in batch_generator(cleaned_chunks, batch_size): # batch here is the actual list of chunks
            tasks = [client.post(api_url, data = {"inputs" : chunk}, headers = headers) for chunk in batch] # create tasks list for complete batch ( creates coroutines, for batch size of 50, a list of 50 coroutines)
            embeddings = await asyncio.gather(*tasks, return_exceptions=True) # wait for all tasks to complete, return_exceptions=True will return the exception if any and prevent crash
            
            total_chunks+= len(batch) # update with the length of batch
            successful_chunks += sum(1 for e in embeddings if isinstance(e, dict) and 'error' not in e) # update with the number of successful chunks, logic is that we check if it is a dictionary ( this ignores any exception objects), and then we also check if 'error' is there in the dict, so errors will also be ignored, rest are successful

            # here is one imp catch: with open is sync, but since writing is fast here, it is not a bottleneck
            with open(output_file_path, 'a') as f: # open the output file in append mode, does not load the whole file into memory, so it is memory efficient, 
                for embedding in embeddings:
                    if isinstance(embedding, dict):
                        f.write(json.dumps(embedding) + '\n')

    end_time = time.perf_counter() # end the timer

    total_time = end_time - start_time # calculate total time

    # create a dictionary to store the metrics
    metrics_dict = {
        'total_chunks' : total_chunks,
        'successful_chunks' : successful_chunks,
        'failed_chunks' : total_chunks - successful_chunks,
        'total_time_pipeline' : total_time,
        'success_rate' : (successful_chunks/total_chunks) * 100 if total_chunks > 0 else 0,
        'throughput' : (total_chunks/total_time) if total_time > 0 else 0
    }

    return metrics_dict

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