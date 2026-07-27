from core.ingestion import FileChunkIterator, read_chunks, clean_chunks, embed_chunks
print("✓ Imports test PASSED")
# define the file path and chunk size
file_path = 'scripts/test_data/100mb_dummy_file.txt'
chunk_size = 1024

# create the pipeline
pipeline = embed_chunks(clean_chunks(read_chunks(file_path, chunk_size)))

chunk_count = 0
for chunk, embedding in pipeline:
    chunk_count += 1
    # Basic assertions
    assert embedding is not None
    assert len(embedding) == 128

print(f"✓ Successfully processed {chunk_count} chunks")
print("✓ Module integration test PASSED")