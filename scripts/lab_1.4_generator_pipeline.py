def read_chunks(file_path, chunk_size):
  with open(file_path, 'r') as f:
    while True:
      chunk = f.read(chunk_size)
      if not chunk:
        break
      yield chunk

def clean_chunks(chunk_stream):
  for chunk in chunk_stream:
    cleaned = ''.join(c for c in chunk if c.isalnum() or c.isspace())
    if cleaned.strip():
      yield cleaned

def embed_chunks(cleaned_chunks):
  for chunk in cleaned_chunks:
    embedding = [hash(chunk + str(i)) % 1000 for i in range(128)]
    yield (chunk, embedding)

def process_file_naive(file_path):
  gc.collect()
  tracemalloc.start()
  #READ
  with open(file_path, 'r') as f:
    content = f.read()
    #create chunks
    chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
    #process all chunks
    for chunk in chunks:
      cleaned = ''.join(c for c in chunk if c.isalnum() or c.isspace())
      embeddings = [hash(cleaned + str(i)) % 1000 for i in range(128)]
  current, peak = tracemalloc.get_traced_memory()
  print(f'current memory using the naive method: {current} bytes, {current/1024:.2f} KB, {current/1024/1024:.2f} MB, \npeak memory using the naive method: {peak} bytes, {peak/1024:.2f} KB, {peak/1024/1024:.2f} MB')
  tracemalloc.stop()
  return current, peak

def generator_approach(file_path, chunk_size):
  gc.collect()
  tracemalloc.start()

  pipeline = embed_chunks(clean_chunks(read_chunks(file_path, chunk_size)))
  for pipe in pipeline:
    pass
  current, peak = tracemalloc.get_traced_memory()
  print(f'current memory using the generator method: {current} bytes, {current/1024:.2f} KB, {current/1024/1024:.2f} MB, \npeak memory using the generator method: {peak} bytes, {peak/1024:.2f} KB, {peak/1024/1024:.2f} MB')
  tracemalloc.stop()
  return current, peak

def benchmark(file_path, chunk_size, benchmark_file_path):
  gc.collect()
  #call the naive function
  current_naive, peak_naive = process_file_naive(file_path)

  gc.collect()  
  #call the generator function
  current_generator, peak_generator = generator_approach(file_path, chunk_size)

  #create a dictionary to store the benchmarks
  benchmarks_dict = {
      'naive': {
          'peak_memory_naive' : f'{peak_naive} bytes, {peak_naive/1024:.2f} KB, {peak_naive/1024/1024:.2f} MB',
          'current_memory_naive' : f'{current_naive} bytes, {current_naive/1024:.2f} KB, {current_naive/1024/1024:.2f} MB'
      },
      'generator': {
          'peak_memory_generator' : f'{peak_generator} bytes, {peak_generator/1024:.2f} KB, {peak_generator/1024/1024:.2f} MB',
          'current_memory_generator' : f'{current_generator} bytes, {current_generator/1024:.2f} KB, {current_generator/1024/1024:.2f} MB'
      }
  }

  # save the benchmarks to a file
  try:
    with open(benchmark_file_path, 'w') as f:
      json.dump(benchmarks_dict, f, indent=4)
    print("File saved")
  except Exception as e:
    print(f'error saving benchmarks file: {e}')

if __name__ == "__main__":
    # import the required modules
    import gc, tracemalloc, json
    # define the file path and chunk size
    file_path = 'scripts/test_data/100mb_dummy_file.txt'
    chunk_size = 1024
    # define the benchmark file path
    # benchmark_file_path = '../../benchmarks/lab_1.4_generator_pipeline_benchmarks.json'
    benchmark_file_path = 'benchmarks/lab_1.4_generator_pipeline_benchmarks.json'
    benchmark(file_path, chunk_size,benchmark_file_path)