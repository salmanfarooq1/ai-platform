from typing import Generator

def embed_chunks(cleaned_chunks: list[str]) -> Generator[tuple[str, list[int]], None, None]:
    '''
    Yield (chunk, embedding) tuples, fake embeddings until a real model is wired in.

    768 dimensions matches nomic-embed-text (local/demo) and is the standardized
    dimension across all deployment modes. See config.py EMBEDDING_DIM.
    hash() keeps values deterministic, sufficient for testing pipeline plumbing.
    '''
    for chunk in cleaned_chunks:
        embedding = [hash(chunk + str(i)) % 1000 for i in range(768)]
        yield (chunk, embedding)