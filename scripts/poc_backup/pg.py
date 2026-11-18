"""Postgres access for backups: always `psql`/`pg_dump`/`pg_restore` inside the stack's own postgres container."""
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from core.database.locks import BACKUP_LOCK_KEY
from scripts.poc_backup.model import DbState
from scripts.poc_lib.context import StackContext
from scripts.poc_lib.runner import CommandError, Session
from scripts.poc_lib.up import DATABASE, PocError

LOCK_WAIT_SECONDS = 120
SCRATCH_PREFIX = "poc_scratch_"

# Everything the manifest binds, in one statement, so the numbers come from one snapshot of one database.
# Counts cover every table of the public schema (zero-row tables included), found by name, not by a fixed list.
STATE_SQL = """
SELECT json_build_object(
  'schema_head', (SELECT version_num FROM alembic_version LIMIT 1),
  'counts', (SELECT COALESCE(json_object_agg(t, c ORDER BY t), '{}'::json) FROM (
      SELECT table_name::text AS t,
             (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name), false, true, '')))[1]::text::bigint AS c
      FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE') s),
  'heads', (SELECT COALESCE(json_agg(json_build_array(tenant_id, position, row_hash) ORDER BY tenant_id), '[]'::json) FROM chain_heads),
  'checkpoints', (SELECT COALESCE(json_agg(json_build_array(tenant_id, position, row_hash, reason) ORDER BY tenant_id, position), '[]'::json) FROM chain_checkpoints),
  'objects', (SELECT COALESCE(json_agg(k ORDER BY k), '[]'::json) FROM (SELECT DISTINCT payload->>'object_key' AS k FROM jobs WHERE payload ? 'object_key') o)
)::text;
"""


def state_of(context: StackContext, db: str = DATABASE) -> DbState:
    text = context.psql(STATE_SQL, db=db).strip()
    try:
        return DbState.from_mapping(json.loads(text))
    except (ValueError, KeyError, TypeError):
        raise PocError("could not read the database state") from None


def lock_args(context: StackContext) -> list[str]:
    return context.argv("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", DATABASE, "-v", "ON_ERROR_STOP=1", "-tAq")


class BackupLock:
    """The exclusive backup lock: a long-lived `psql` session. Closing it (or losing the process: the pipe closes) ends the
    database session, and Postgres releases the lock. `assert_held` proves it is still held, from the database's own view."""

    def __init__(self, session: Session, pid: int) -> None:
        self.session, self.pid = session, pid

    def close(self) -> None:
        self.session.close()

    def assert_held(self, context: StackContext) -> None:
        """Raise unless the psql client is alive AND pg_locks lists this session's pid as granted holder of the key."""
        if self.session.poll() is not None:
            raise PocError("backup lock lost: the lock session ended while the backup was running; nothing was published")
        try:
            held = context.psql(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND objsubid = 1 AND mode = 'ExclusiveLock' "
                f"AND pid = {self.pid} AND classid = {BACKUP_LOCK_KEY >> 32} AND objid = {BACKUP_LOCK_KEY & 0xFFFFFFFF}").strip()
        except CommandError:
            raise PocError("backup lock could not be verified (the database is unreachable); nothing was published") from None
        if held != "1":
            raise PocError("backup lock lost: the database no longer lists this backup as the lock holder; nothing was published")


def take_backup_lock(context: StackContext) -> BackupLock:
    """Start a long-lived `psql` in the postgres container that holds the exclusive backup lock until it is closed.

    Waits up to LOCK_WAIT_SECONDS for an in-flight purge, then fails with a clean error. The session reports its own
    backend pid so the backup can later prove, in `pg_locks`, that it still holds the lock.
    """
    session = context.runner.spawn(lock_args(context), env=context.env)
    pid: int | None = None
    try:
        session.write(f"SET lock_timeout = '{LOCK_WAIT_SECONDS}s';\nSELECT pg_advisory_lock({BACKUP_LOCK_KEY});\n"
                      "SELECT pg_backend_pid();\n\\echo LOCKED\n".encode())
        while True:
            line = session.readline(LOCK_WAIT_SECONDS + 30).strip()
            if line == "LOCKED":
                if pid is None:
                    raise PocError("could not take the backup lock (the lock session did not report its backend)")
                return BackupLock(session, pid)
            if line.isdigit():
                pid = int(line)
            elif line == "" and session.poll() is not None:
                raise PocError("could not take the backup lock (a purge is in flight or the database is unreachable)")
    except TimeoutError:
        session.close()
        raise PocError("could not take the backup lock in time (a purge is in flight or the database is unreachable)") from None
    except BaseException:
        session.close()
        raise


@contextmanager
def scratch_database(context: StackContext) -> Iterator[str]:
    """An owned throw-away database for checking a dump. Always dropped, also on failure."""
    name = SCRATCH_PREFIX + secrets.token_hex(4)
    context.psql(f'CREATE DATABASE "{name}"', db="postgres")
    try:
        yield name
    finally:
        context.runner.run(context.argv("exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "postgres", "-tAq", "-c",
                                        f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'), env=context.env, check=False)


def restore_dump(context: StackContext, dump: Path, db: str) -> None:
    """Load a custom-format dump into an existing database, in one transaction, stopping at the first error."""
    context.compose("exec", "-T", "postgres", "pg_restore", "-U", "postgres", "-d", db, "--no-owner", "--exit-on-error",
                    "--single-transaction", input_file=dump)
