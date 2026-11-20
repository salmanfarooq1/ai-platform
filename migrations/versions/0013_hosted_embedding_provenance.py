"""Relabel hosted embedding provenance to the runtime label (hosted-deploy fix).

The runtime labels a vector `alias@digest` for a local model and `alias@provider_model_id` for a hosted one, where the
hosted provider model id is the alias after its first `/` (adapters/model_catalog.py). Migration 0007 labelled existing
rows with the bare alias, so a hosted deploy counted every row as stale and refused search. This appends the hosted
model id to each bare hosted label. Local (`ollama/`) labels and labels that already carry `@` are left alone, so the
migration is idempotent. Each tenant is updated under its own `app.tenant_id`, as in 0007, so row-level security holds.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

RELABEL = """
DO $$
DECLARE t UUID;
BEGIN
    FOR t IN SELECT id FROM tenants LOOP
        PERFORM set_config('app.tenant_id', t::text, true);
        UPDATE documents
        SET embedding_model = embedding_model || '@' || substring(embedding_model FROM position('/' IN embedding_model) + 1)
        WHERE tenant_id = t
          AND position('@' IN embedding_model) = 0
          AND embedding_model NOT LIKE 'ollama/%'
          AND position('/' IN embedding_model) > 1
          AND position('/' IN embedding_model) < length(embedding_model);
    END LOOP;
    PERFORM set_config('app.tenant_id', '', true);
END
$$
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(RELABEL)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
