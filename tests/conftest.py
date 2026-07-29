"""
tests/conftest.py

Shared config for the whole suite. Auto-tags every test with a tier
marker (unit / integration / e2e) based on which directory it lives in.

Run subsets with:
    poetry run pytest -m unit
    poetry run pytest -m integration
    poetry run pytest -m e2e
    poetry run pytest                 # everything
"""
import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        parts = item.path.parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
        elif "e2e" in parts:
            item.add_marker(pytest.mark.e2e)
