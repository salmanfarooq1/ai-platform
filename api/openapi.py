"""Canonical OpenAPI rendering, shared by scripts/update_openapi.py and the snapshot test."""
import json
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def render_openapi() -> str:
    """The app's OpenAPI document as stable, sorted JSON text."""
    from api.main import create_app

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
