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