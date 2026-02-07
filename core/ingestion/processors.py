def clean_chunks(chunk_stream):
  for chunk in chunk_stream:
    cleaned = ''.join(c for c in chunk if c.isalnum() or c.isspace())
    if cleaned.strip():
      yield cleaned