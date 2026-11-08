"""scripts/check_skips.py: the CI skip check allows only the live-SeaweedFS skips of the object store contract."""
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_spec = importlib.util.spec_from_file_location("check_skips", Path(__file__).parents[2] / "scripts" / "check_skips.py")
check_skips = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_skips)

CONTRACT = "tests.contracts.test_object_store_contract"
LIVE_REASON = "live SeaweedFS not configured; set S3_LIVE_ENDPOINT (scripts/verify/seaweedfs.sh)"


def report(tmp_path, cases):
    body = "".join(
        f'<testcase classname="{c}" name="{n}"><skipped type="pytest.skip" message="{r}"/></testcase>' for c, n, r in cases)
    path = tmp_path / "report.xml"
    path.write_text(f'<testsuites><testsuite name="pytest">{body}<testcase classname="x" name="passes"/></testsuite></testsuites>')
    return str(path)


def seaweed_cases(n):
    return [(CONTRACT, f"test_case_{i}[seaweedfs]", LIVE_REASON) for i in range(n)]


def test_only_live_minio_skips_of_the_contract_pass(tmp_path):
    assert check_skips.check(report(tmp_path, seaweed_cases(10)), expect=10) == []
    empty = tmp_path / "empty-allowlist.json"
    empty.write_text("[]")
    assert check_skips.check(report(tmp_path, []), expect=None, allowlist=empty) == []
    assert check_skips.check(report(tmp_path, []))  # Default allowlist requires ten.


def test_a_skip_in_another_file_fails_even_with_the_minio_reason(tmp_path):
    cases = seaweed_cases(2) + [("tests.integration.test_rls", "test_x[seaweedfs]", LIVE_REASON)]
    assert check_skips.check(report(tmp_path, cases))


def test_a_skip_in_the_contract_with_another_reason_fails(tmp_path):
    cases = seaweed_cases(2) + [(CONTRACT, "test_y[seaweedfs]", "Redis is not reachable")]
    assert check_skips.check(report(tmp_path, cases))


def test_a_skip_in_the_contract_that_is_not_the_minio_parameter_fails(tmp_path):
    cases = seaweed_cases(2) + [(CONTRACT, "test_z[local]", LIVE_REASON)]
    assert check_skips.check(report(tmp_path, cases))


def test_a_different_skip_count_fails(tmp_path):
    assert check_skips.check(report(tmp_path, seaweed_cases(9)), expect=10)
    assert check_skips.check(report(tmp_path, seaweed_cases(11)), expect=10)


def test_the_command_exits_non_zero_on_a_bad_report(tmp_path):
    assert check_skips.main([report(tmp_path, seaweed_cases(10)), "--expect", "10"]) == 0
    assert check_skips.main([report(tmp_path, [("a.b", "t", "Postgres is not reachable")])]) == 1


def test_missing_allowlist_fails(tmp_path):
    assert check_skips.main([report(tmp_path, seaweed_cases(10)), "--allowlist", str(tmp_path / "missing.json")]) == 1


def test_custom_allowlist_requires_exact_count_per_entry(tmp_path):
    import json

    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps([{
        "classname": CONTRACT, "name_contains": "[seaweedfs", "reason_prefix": "live SeaweedFS not configured",
        "count": 1, "why": "The live service is optional here.",
    }]))
    assert check_skips.check(report(tmp_path, seaweed_cases(1)), allowlist=allowlist) == []
    assert check_skips.check(report(tmp_path, seaweed_cases(2)), allowlist=allowlist)


def test_cli_cannot_override_the_allowlist_count(tmp_path):
    assert check_skips.main([report(tmp_path, seaweed_cases(9)), "--expect", "9"]) == 1


def test_previous_minio_skips_are_rejected_after_backend_transition(tmp_path):
    previous = [(CONTRACT, f"test_case_{index}[minio]", "live MinIO not available") for index in range(10)]
    assert check_skips.check(report(tmp_path, previous))
