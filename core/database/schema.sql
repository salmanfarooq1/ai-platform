CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL DEFAULT 'default',
    content TEXT,
    embedding VECTOR(768),
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_documents_namespace 
    ON documents(namespace);

CREATE INDEX IF NOT EXISTS idx_documents_document_id 
    ON documents(document_id);

-- HNSW index for sub-linear vector similarity search.
-- Without this, every /search call does a full sequential scan: O(N) per query.
-- With HNSW, search is approximate O(log N) — essential once the table exceeds ~10k rows.
--
-- m=16: connections per graph node. Higher = better recall, more memory. 16 is the standard default.
-- ef_construction=64: search depth during index build. Higher = better quality, slower build.
-- vector_cosine_ops: must match the <=> operator used in queries.
--
-- To apply to an existing populated table without locking, run via psql:
--   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_documents_embedding_hnsw
--       ON documents USING hnsw (embedding vector_cosine_ops)
--       WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);