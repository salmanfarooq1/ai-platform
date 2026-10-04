"""Baseline: the schema that core/database/schema.sql used to define.

Idempotent by design (IF NOT EXISTS / CREATE OR REPLACE). On the hosted database
that already has every table this migration changes nothing except recording the
Alembic version.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE EXTENSION IF NOT EXISTS vector""",
    """CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    namespace VARCHAR(255) NOT NULL DEFAULT 'default',
    content TEXT,
    embedding VECTOR(768),
    metadata JSONB,
    fts_vector tsvector
)""",
    """CREATE INDEX IF NOT EXISTS idx_documents_namespace
    ON documents(namespace)""",
    """CREATE INDEX IF NOT EXISTS idx_documents_document_id
    ON documents(document_id)""",
    """CREATE INDEX IF NOT EXISTS idx_documents_ns_docid
    ON documents(namespace, document_id)""",
    """CREATE INDEX IF NOT EXISTS idx_documents_embedding_hnsw
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)""",
    """CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents USING GIN (fts_vector)""",
    """CREATE OR REPLACE FUNCTION update_fts_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fts_vector := to_tsvector('english', coalesce(NEW.content, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql""",
    """DROP TRIGGER IF EXISTS trig_update_fts ON documents""",
    """CREATE TRIGGER trig_update_fts
    BEFORE INSERT OR UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_fts_vector()""",
    """CREATE TABLE IF NOT EXISTS document_registry (
    document_id     VARCHAR(255) NOT NULL,
    namespace       VARCHAR(255) NOT NULL DEFAULT 'default',
    content_hash    VARCHAR(64)  NOT NULL,
    source_filename VARCHAR(500),
    chunk_count     INTEGER      NOT NULL DEFAULT 0,
    last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (document_id, namespace)
)""",
    """CREATE TABLE IF NOT EXISTS usage_log (
    id                BIGSERIAL PRIMARY KEY,
    request_id        VARCHAR(64)   NOT NULL,
    endpoint          VARCHAR(100)  NOT NULL,
    namespace         VARCHAR(255)  NOT NULL DEFAULT 'global',
    model             VARCHAR(200)  NOT NULL,
    prompt_tokens     INTEGER       NOT NULL DEFAULT 0,
    completion_tokens INTEGER       NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(12,8) NOT NULL DEFAULT 0.0,
    routing_decision  VARCHAR(50),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW()
)""",
    """CREATE INDEX IF NOT EXISTS idx_usage_log_created
    ON usage_log(created_at DESC)""",
    """CREATE INDEX IF NOT EXISTS idx_usage_log_endpoint_date
    ON usage_log(endpoint, created_at)""",
    """CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL PRIMARY KEY,
    request_id  TEXT          NOT NULL,
    endpoint    TEXT          NOT NULL,
    rating      TEXT          NOT NULL CHECK (rating IN ('up', 'down')),
    comment     TEXT,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
)""",
    """CREATE INDEX IF NOT EXISTS idx_feedback_request_id
    ON feedback(request_id)""",
    """CREATE INDEX IF NOT EXISTS idx_feedback_created
    ON feedback(created_at DESC)""",
]


def upgrade() -> None:
    bind = op.get_bind()
    for statement in STATEMENTS:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
