#!/usr/bin/env python3
"""Require the exact skips in tests/skip_allowlist.json.

Usage: scripts/check_skips.py REPORT.xml [--allowlist PATH]
The optional legacy --expect must agree with the allowlist; it cannot override it.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_ALLOWLIST = Path(__file__).resolve().parents[1] / "tests" / "skip_allowlist.json"


def skips(report: str) -> list[tuple[str, str, str]]:
    """(classname, name, reason) for each skipped test case."""
    found = []
    for case in ET.parse(report).getroot().iter("testcase"):
        skipped = case.find("skipped")
        if skipped is not None:
            found.append((case.get("classname", ""), case.get("name", ""), skipped.get("message", "")))
    return found


def check(report: str, expect: int | None = None, *, allowlist: Path = DEFAULT_ALLOWLIST) -> list[str]:
    """Missing files, ambiguous matches, unknown skips and count drift all fail."""
    try:
        entries = json.loads(allowlist.read_text())
        if not isinstance(entries, list):
            raise ValueError("allowlist must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"classname", "name_contains", "reason_prefix", "count", "why"}:
                raise ValueError("invalid allowlist entry fields")
            if any(not isinstance(entry[k], str) or not entry[k].strip() for k in ("classname", "name_contains", "reason_prefix", "why")):
                raise ValueError("entry strings must be nonempty")
            if type(entry["count"]) is not int or entry["count"] < 1:
                raise ValueError("entry count must be a positive integer")
        found = skips(report)
    except (OSError, ValueError, ET.ParseError) as exc:
        return [f"skip check failed: {exc}"]
    expected = sum(e["count"] for e in entries)
    problems = []
    if expect is not None and expect != expected:
        problems.append(f"--expect {expect} disagrees with allowlist count {expected}")
    counts = [0] * len(entries)
    for classname, name, reason in found:
        matches = [i for i, e in enumerate(entries) if classname == e["classname"] and e["name_contains"] in name and reason.startswith(e["reason_prefix"])]
        if len(matches) != 1:
            problems.append(f"unexpected or ambiguous skip: {classname}::{name} ({reason})")
        else:
            counts[matches[0]] += 1
    for entry, count in zip(entries, counts):
        if count != entry["count"]:
            problems.append(f"expected exactly {entry['count']} skips for {entry['classname']} {entry['name_contains']}, found {count}")
    if len(found) != expected:
        problems.append(f"expected exactly {expected} total skips, found {len(found)}")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--expect", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    problems = check(args.report, args.expect, allowlist=args.allowlist)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"skip check ok: {len(skips(args.report))} allowed skips")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
