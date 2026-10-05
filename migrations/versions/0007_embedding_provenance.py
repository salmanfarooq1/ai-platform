"""Embedding provenance and run provenance (Sprint 006).

`documents` gets `embedding_model` and `embedding_dim`: the model and width that produced each vector (strict
rule 12). Existing rows are backfilled with the configured embedding model (`EMBED_MODEL`; for the hosted
preview that is the public-preview model) and with the real width of each vector (`vector_dims(embedding)`).
Before that, a check fails the migration if any vector has another width than the configured `EMBEDDING_DIM`:
a row is never labelled with a width it does not have. Then both columns become NOT NULL, and an index
serves the provenance filter that retrieval adds. Retrieval compares only vectors of the active model and
dimension; the rest are counted by `count_stale_vectors` for `/v1/health`.

`gateway_decisions` gets a nullable `execution_id uuid` (the agent run that caused the decision, ADR-0009) and
an index on it. The column is nullable: most decisions belong to no run.

The backfill and the count walk the tenants and set `app.tenant_id` for each, so they work for an owner role
that is subject to the forced row-level security as well as for a superuser. No grant changes: same tables.
`count_stale_vectors` is a narrow SECURITY DEFINER function (same audited pattern as `auth_lookup_*`): it returns
one number and no row content, and `gap_app` may execute it.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

from core.settings import get_settings

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

ADD_COLUMNS = [
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model TEXT",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dim INTEGER",
    "ALTER TABLE gateway_decisions ADD COLUMN IF NOT EXISTS execution_id UUID",
]

BACKFILL = """
DO $$
DECLARE t UUID;
BEGIN
    FOR t IN SELECT id FROM tenants LOOP
        PERFORM set_config('app.tenant_id', t::text, true);
        UPDATE documents SET embedding_model = %(model)s, embedding_dim = coalesce(vector_dims(embedding), %(dim)s)
        WHERE tenant_id = t AND (embedding_model IS NULL OR embedding_dim IS NULL);
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$
"""

CONSTRAINTS_AND_INDEXES = [
    "ALTER TABLE documents ALTER COLUMN embedding_model SET NOT NULL",
    "ALTER TABLE documents ALTER COLUMN embedding_dim SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_documents_embedding_provenance "
    "ON documents(tenant_id, namespace, embedding_model, embedding_dim)",
    "CREATE INDEX IF NOT EXISTS idx_gateway_decisions_execution "
    "ON gateway_decisions(tenant_id, execution_id) WHERE execution_id IS NOT NULL",
    """CREATE OR REPLACE FUNCTION count_stale_vectors(p_model TEXT, p_dim INTEGER)
RETURNS BIGINT
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    t UUID;
    n BIGINT;
    total BIGINT := 0;
    previous TEXT := coalesce(current_setting('app.tenant_id', true), '');
BEGIN
    FOR t IN SELECT id FROM tenants LOOP
        PERFORM set_config('app.tenant_id', t::text, true);
        SELECT count(*) INTO n FROM documents
        WHERE tenant_id = t AND (embedding_model IS DISTINCT FROM p_model OR embedding_dim IS DISTINCT FROM p_dim);
        total := total + n;
    END LOOP;
    PERFORM set_config('app.tenant_id', previous, true);
    RETURN total;
END
$$""",
    "REVOKE ALL ON FUNCTION count_stale_vectors(TEXT, INTEGER) FROM PUBLIC",
    """DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'gap_app') THEN
        GRANT EXECUTE ON FUNCTION count_stale_vectors(TEXT, INTEGER) TO gap_app;
    END IF;
END
$$""",
]


def check_vector_widths(bind, expected_dim: int) -> None:
    """Fail, naming the mismatch, if any stored vector is not `expected_dim` wide. Walks the tenants (row-level
    security), like the backfill."""
    mismatched: dict[int, int] = {}
    for (tenant_id,) in bind.exec_driver_sql("SELECT id FROM tenants").fetchall():
        bind.exec_driver_sql("SELECT set_config('app.tenant_id', %(t)s, true)", {"t": str(tenant_id)})
        rows = bind.exec_driver_sql(
            "SELECT vector_dims(embedding), count(*) FROM documents "
            "WHERE tenant_id = %(t)s AND embedding IS NOT NULL AND vector_dims(embedding) <> %(dim)s GROUP BY 1",
            {"t": str(tenant_id), "dim": expected_dim},
        ).fetchall()
        for width, count in rows:
            mismatched[width] = mismatched.get(width, 0) + count
    bind.exec_driver_sql("SELECT set_config('app.tenant_id', '', true)")
    if mismatched:
        found = ", ".join(f"{count} vector(s) of width {width}" for width, count in sorted(mismatched.items()))
        raise RuntimeError(
            f"Migration 0007 refused: EMBEDDING_DIM is {expected_dim} but documents holds {found}. "
            "Set EMBEDDING_DIM to the width of the stored vectors, or re-embed them, then run the migration again."
        )


def upgrade() -> None:
    bind = op.get_bind()
    settings = get_settings()
    check_vector_widths(bind, settings.embedding_dim)
    for statement in ADD_COLUMNS:
        bind.exec_driver_sql(statement)
    bind.exec_driver_sql(BACKFILL, {"model": settings.embed_model, "dim": settings.embedding_dim})
    for statement in CONSTRAINTS_AND_INDEXES:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
