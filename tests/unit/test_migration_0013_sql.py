"""Migration 0013 runs its SQL through alembic's `exec_driver_sql`, which formats `%` as a driver placeholder.

A `%` in that SQL (for example `LIKE 'ollama/%'`) crashed the hosted deploy at startup, so the SQL must carry none.
"""
import importlib.util
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0013_hosted_embedding_provenance.py"


def test_relabel_sql_has_no_percent_sign() -> None:
    spec = importlib.util.spec_from_file_location("m0013", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "%" not in module.RELABEL
