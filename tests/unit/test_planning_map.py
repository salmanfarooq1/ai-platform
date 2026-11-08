"""The platform map is the single entry point every session loads, so its size is a budget, not a guideline."""
from pathlib import Path

import pytest

MAP = Path(__file__).resolve().parents[2] / "planning" / "MAP.md"
MAX_LINES = 160
MAX_NOW_LINES = 15

pytestmark = pytest.mark.unit


def test_map_stays_within_its_line_budget() -> None:
    lines = MAP.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_LINES, f"planning/MAP.md has {len(lines)} lines; move history to sprint reports or CHANGELOG.md"


def test_now_section_stays_short() -> None:
    text = MAP.read_text(encoding="utf-8")
    assert "\n## Now" in text, "planning/MAP.md must keep a '## Now' section"
    now = text.split("\n## Now", 1)[1].split("\n## ", 1)[0]
    filled = [line for line in now.splitlines()[1:] if line.strip()]
    assert len(filled) <= MAX_NOW_LINES, f"'Now' has {len(filled)} lines; keep it to the current state only"
