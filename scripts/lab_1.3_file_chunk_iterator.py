class FileChunkIterator:
    def __init__(self, file_path, chunk_size):
        # we define the file path and chunk size, and open the file in binary read mode.
        # using 'open' function, we are essentially creating our own context manager wrapper.
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.file = open(file_path, 'rb') 

    # now we define the __iter__ method, which is used to get an iterator from the FileChunkIterator class.
    # it would essentially convert our FileChunkIterator class into an iterator.

    def __iter__(self):
        return self

    # now we define the __next__ method, which is used to get the next chunk from the FileChunkIterator class.
    # it would essentially read the file in chunks of size chunk_size and return the next chunk.
    # if the file is empty, it would raise StopIteration.
    # we are raising the StopIteration exception when file is empty, we are not using file.tell() or file.seek() because 
    # python automatically handles the file pointer, when we have an 'open' object, it would automatically 
    # keep track of the file pointer.
    # NOTE: we have self.file.close() here because we are handeling the case of user not using the 'with' context manager here.
    
    def __next__(self):
        chunk = self.file.read(self.chunk_size)
        if not chunk:
            self.file.close()
            raise StopIteration
        return chunk
    
    # now we define the __enter__ method, which is for the context manager, it is called when 'with' is called.
    # it would essentially return the iterator object.
    
    def __enter__(self):
        return self
  
    # now we define the __exit__ method, which is for the context manager, it is called automatically to close the file.
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.file.closed:
            self.file.close()

def benchmark(file_path, chunk_size,benchmark_file_path):

  '''
  This function benchmarks the adhoc and smart methods and saves the benchmarks to a file.
  '''
  # using ad hoc method, collect the garbage manually so that python cleans any trash first.
  gc.collect()
  # start tracing memory
  tracemalloc.start()
  # call the adhoc function, this would expectedly use more memory because it reads the entire file at once.
  file_content_adhoc, file_len_adhoc = test_ad_hoc(file_path)
  # get the current and peak memory usage
  current_adhoc, peak_adhoc = tracemalloc.get_traced_memory()
  # stop tracing memory
  tracemalloc.stop()

  # using our FileChunkIterator
  gc.collect()
  # start tracing memory
  tracemalloc.start()
  # call the smart function, this would expectedly use less memory because it reads the file in chunks.
  file_content_smart, file_len_smart = test_smart(file_path, chunk_size)
  # get the current and peak memory usage
  current_smart, peak_smart = tracemalloc.get_traced_memory()
  # stop tracing memory
  tracemalloc.stop()

  # create a dictionary to store the benchmarks
  benchmarks_dict = {
      'adhoc': {
          'peak_memory_adhoc' : f'{peak_adhoc} bytes, {peak_adhoc/1024:.2f} KB, {peak_adhoc/1024/1024:.2f} MB',    
          'current_memory_adhoc' : f'{current_adhoc} bytes, {current_adhoc/1024:.2f} KB, {current_adhoc/1024/1024:.2f} MB'
      },
      'smart': {
          'peak_memory_smart' : f'{peak_smart} bytes, {peak_smart/1024:.2f} KB, {peak_smart/1024/1024:.2f} MB',
          'current_memory_smart' : f'{current_smart} bytes, {current_smart/1024:.2f} KB, {current_smart/1024/1024:.2f} MB'   
      }
  }

  # save the benchmarks to a file
  try:
    with open(benchmark_file_path, 'w') as f:
      json.dump(benchmarks_dict, f, indent=4)
    print("File saved")
  except Exception as e:
    print(f'error saving benchmarks file: {e}')
   


def test_ad_hoc(file_path):
  '''
  This function reads the entire file at once and returns the file content and file length.
  '''
  with open (file_path, 'rb') as f:
    file_content = f.read()
    file_len = len(file_content)
    return file_content, file_len

def test_smart(file_path, chunk_size):
  '''
  This function reads the file in chunks of size chunk_size, using our custom defined FileChunkIterator(iterator + context manager) and returns the file length.
  '''
  file_len = 0
  with FileChunkIterator(file_path, chunk_size) as f:
    for chunk in f:
      file_len += len(chunk)
  return None, file_len

if __name__ == "__main__":
    # import the required modules
    import gc, tracemalloc, json
    # define the file path and chunk size
    file_path = 'test_data/100mb_dummy_file.txt'
    chunk_size = 1024
    # define the benchmark file path
    benchmark_file_path = '../benchmarks/lab_1.3_file_chunk_iterator_benchmarks.json'
    # call the benchmark function
    benchmark(file_path, chunk_size,benchmark_file_path)

