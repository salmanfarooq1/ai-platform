"""Regenerate docs/openapi.json from the app. Run after any intentional API change:

    poetry run python scripts/update_openapi.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.openapi import SNAPSHOT_PATH, render_openapi  # noqa: E402 - needs the sys.path line above

if __name__ == "__main__":
    SNAPSHOT_PATH.write_text(render_openapi())
    print(f"wrote {SNAPSHOT_PATH}")
