# comprehensive custom made generator class for lazy file reading

class FileChunkIterator:
    def __init__(self, file_path, chunk_size):
        # we define the file path and chunk size, and open the file in binary read mode.
        # using 'open' function, we are essentially creating our own context manager wrapper.
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.file = None

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
        self.file = open(self.file_path, 'rb')
        if self.file is None:
            raise RuntimeError("Use 'with FileChunkIterator(...) as it:' to iterate")
        return self
  
    # now we define the __exit__ method, which is for the context manager, it is called automatically to close the file.
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.file.closed:
            self.file.close()

# simpler generator function 

def read_chunks(file_path, chunk_size):
  with open(file_path, 'r') as f:
    while True:
      chunk = f.read(chunk_size)
      if not chunk:
        break
      yield chunk