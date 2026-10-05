#!/usr/bin/env python3
"""Fail unless every skip in a pytest JUnit XML report is the live-MinIO skip of the object store contract.

Usage: scripts/check_skips.py REPORT.xml [--expect N]

An allowed skip has all three of:
  - a test in tests/contracts/test_object_store_contract.py (JUnit classname `tests.contracts.test_object_store_contract`),
  - the `minio` parameter (`test_x[minio...]`),
  - the reason `live MinIO not available`.
Any other skip fails. With --expect N the number of skips must be exactly N, so a changed pattern fails too.
"""
import sys
import xml.etree.ElementTree as ET

ALLOWED_CLASS = "tests.contracts.test_object_store_contract"
ALLOWED_REASON = "live MinIO not available"


def skips(report: str) -> list[tuple[str, str, str]]:
    """(classname, name, reason) for each skipped test case."""
    found = []
    for case in ET.parse(report).getroot().iter("testcase"):
        skipped = case.find("skipped")
        if skipped is not None:
            found.append((case.get("classname", ""), case.get("name", ""), skipped.get("message", "")))
    return found


def is_allowed(classname: str, name: str, reason: str) -> bool:
    return classname == ALLOWED_CLASS and "[minio" in name and reason.startswith(ALLOWED_REASON)


def check(report: str, expect: int | None = None) -> list[str]:
    """The problems found, empty when the report is clean."""
    found = skips(report)
    problems = [f"unexpected skip: {c}::{n} ({r})" for c, n, r in found if not is_allowed(c, n, r)]
    if expect is not None and len(found) != expect:
        problems.append(f"expected exactly {expect} live-MinIO skips, found {len(found)} skips")
    return problems


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    expect = int(argv[argv.index("--expect") + 1]) if "--expect" in argv else None
    problems = check(argv[0], expect)
    for problem in problems:
        print(problem)
    if problems:
        print("Integration/e2e tests were skipped. Failing the job.")
        return 1
    print(f"skip check ok: {len(skips(argv[0]))} allowed live-MinIO skips")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
