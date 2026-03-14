def embed_chunks(cleaned_chunks):
  for chunk in cleaned_chunks:
    embedding = [hash(chunk + str(i)) % 1000 for i in range(768)]
    yield (chunk, embedding)