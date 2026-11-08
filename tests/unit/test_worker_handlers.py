"""The worker composes only handlers belonging to enabled modules."""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from core.settings import Settings
from workers.context import build_handlers

pytestmark = pytest.mark.unit


def _build(enabled_modules: str, *, agent_graph=None):
    settings = Settings(_env_file=None, enabled_modules=enabled_modules)
    adapters = SimpleNamespace(
        events=object(), knowledge=object(), embeddings=object(), objects=object(),
    )
    keyring = SimpleNamespace(sign=lambda _text: ("signature", "key"))
    return build_handlers(
        adapters, object(), object(), agent_graph=agent_graph, settings=settings, keyring=keyring,
    )


def test_gateway_edition_registers_ingest_and_purge_only():
    assert set(_build("gateway")) == {"ingest", "purge_decisions"}


def test_agents_edition_adds_agent_run():
    assert set(_build("gateway,agents", agent_graph=object())) == {
        "ingest", "purge_decisions", "agent_run",
    }


def test_worker_context_imports_no_agent_code():
    script = """
import sys
from types import SimpleNamespace
from core.settings import Settings
from workers.context import build_handlers

adapters = SimpleNamespace(events=object(), knowledge=object(), embeddings=object(), objects=object())
keyring = SimpleNamespace(sign=lambda text: ("signature", "key"))
build_handlers(adapters, object(), object(), settings=Settings(_env_file=None, enabled_modules="gateway"), keyring=keyring)
blocked = ("api.agent", "api.mcp", "sandbox_agent", "langgraph", "openshell")
assert not [name for name in sys.modules if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked)]
"""
    result = subprocess.run(
        [sys.executable, "-c", script], check=False, capture_output=True, text=True, env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
