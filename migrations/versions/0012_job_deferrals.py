"""How often a job was put off, not failed (Sprint 015).

`jobs.deferrals` counts the deferrals of a job: a handler that must wait for something outside itself (a backup holding
the shared lock, for example) puts the job back as `queued` for later without using an attempt. The count keeps that
visible on the job row, in its read model and in the worker log. Existing rows get 0. Nothing else changes: the
tenant-isolation policy and the app role's table-level grants of 0008 already cover the new column.
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

STATEMENTS = (
    "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS deferrals INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_deferrals_check",
    "ALTER TABLE jobs ADD CONSTRAINT jobs_deferrals_check CHECK (deferrals >= 0)",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in STATEMENTS:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise NotImplementedError("Migrations are forward-only (strict rule 7).")
