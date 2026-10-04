"""Alembic environment: synchronous, SQL-first, DSN from core.settings.

A DSN can also be passed programmatically with
`Config.set_main_option("sqlalchemy.url", dsn)`; the test harness does this to
migrate a throwaway database.

Seam for later: set `target_metadata` to a SQLAlchemy MetaData to enable
autogenerate and a schema-drift check. There are no ORM models yet.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def _database_url() -> str:
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        url = explicit
    else:
        from core.settings import get_settings

        url = get_settings().migration_dsn
    # SQLAlchemy 2.1 maps a bare "postgresql://" to psycopg 3. The project ships psycopg2.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
