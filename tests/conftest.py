"""
tests/conftest.py

Shared config for the whole suite. Auto-tags every test with a tier
marker (unit / integration / e2e) based on which directory it lives in (tests/contracts counts as integration),
and installs the network guard for every test.

Run subsets with:
    poetry run pytest -m unit
    poetry run pytest -m integration
    poetry run pytest -m e2e
    poetry run pytest                 # everything
"""
import ipaddress
import socket
from typing import Any

import litellm
import pytest

from tests.fakes import NetworkBlockedError, blocked

# Fixtures shared by the integration and e2e tiers.
pytest_plugins = ["tests.db_fixtures"]


def pytest_collection_modifyitems(config, items):
    for item in items:
        parts = item.path.parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts or "contracts" in parts:
            # The contract suites run every adapter of a port, the real ones (Postgres, Redis) included.
            item.add_marker(pytest.mark.integration)
        elif "e2e" in parts:
            item.add_marker(pytest.mark.e2e)


def _is_local(host: Any) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Guard: no real LLM, embedding or internet call can happen in any test.

    - litellm entry points raise NetworkBlockedError unless a test installs a fake.
    - Sockets may only connect to loopback addresses (Postgres and Redis run locally).
    """
    for name in ("acompletion", "completion", "aembedding", "embedding"):
        monkeypatch.setattr(litellm, name, blocked(name))

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        if isinstance(address, tuple) and not _is_local(address[0]):
            raise NetworkBlockedError(f"Test tried to open a socket to {address[0]!r}. Only loopback is allowed.")
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        if isinstance(address, tuple) and not _is_local(address[0]):
            raise NetworkBlockedError(f"Test tried to open a socket to {address[0]!r}. Only loopback is allowed.")
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _is_local(host):
            raise NetworkBlockedError(f"Test tried to resolve {host!r}. Only loopback is allowed.")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield
