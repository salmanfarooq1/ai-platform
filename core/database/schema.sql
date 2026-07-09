CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL DEFAULT 'default',
    content TEXT,
    embedding VECTOR(768),
    metadata JSONB,
    fts_vector tsvector
);

CREATE INDEX IF NOT EXISTS idx_documents_namespace 
    ON documents(namespace);

CREATE INDEX IF NOT EXISTS idx_documents_document_id 
    ON documents(document_id);

CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (BM25-style keyword search) support — Week 7
-- fts_vector is declared in the table above for fresh installs.
-- The statements below backfill existing rows, index the column, and keep
-- it in sync on future writes. Safe to re-run (idempotent).

CREATE INDEX IF NOT EXISTS idx_documents_fts 
    ON documents USING GIN (fts_vector);

CREATE OR REPLACE FUNCTION update_fts_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fts_vector := to_tsvector('english', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trig_update_fts ON documents;
CREATE TRIGGER trig_update_fts
    BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_fts_vector();