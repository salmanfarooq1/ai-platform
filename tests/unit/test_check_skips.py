"""scripts/check_skips.py: the CI skip check allows only the live-MinIO skips of the object store contract."""
import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_spec = importlib.util.spec_from_file_location("check_skips", Path(__file__).parents[2] / "scripts" / "check_skips.py")
check_skips = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_skips)

CONTRACT = "tests.contracts.test_object_store_contract"
MINIO_REASON = "live MinIO not available here (image not pullable); set MINIO_ENDPOINT (scripts/verify/minio.sh)"


def report(tmp_path, cases):
    body = "".join(
        f'<testcase classname="{c}" name="{n}"><skipped type="pytest.skip" message="{r}"/></testcase>' for c, n, r in cases)
    path = tmp_path / "report.xml"
    path.write_text(f'<testsuites><testsuite name="pytest">{body}<testcase classname="x" name="passes"/></testsuite></testsuites>')
    return str(path)


def minio_cases(n):
    return [(CONTRACT, f"test_case_{i}[minio]", MINIO_REASON) for i in range(n)]


def test_only_live_minio_skips_of_the_contract_pass(tmp_path):
    assert check_skips.check(report(tmp_path, minio_cases(10)), expect=10) == []
    assert check_skips.check(report(tmp_path, []), expect=None) == []


def test_a_skip_in_another_file_fails_even_with_the_minio_reason(tmp_path):
    cases = minio_cases(2) + [("tests.integration.test_rls", "test_x[minio]", MINIO_REASON)]
    assert check_skips.check(report(tmp_path, cases))


def test_a_skip_in_the_contract_with_another_reason_fails(tmp_path):
    cases = minio_cases(2) + [(CONTRACT, "test_y[minio]", "Redis is not reachable")]
    assert check_skips.check(report(tmp_path, cases))


def test_a_skip_in_the_contract_that_is_not_the_minio_parameter_fails(tmp_path):
    cases = minio_cases(2) + [(CONTRACT, "test_z[local]", MINIO_REASON)]
    assert check_skips.check(report(tmp_path, cases))


def test_a_different_skip_count_fails(tmp_path):
    assert check_skips.check(report(tmp_path, minio_cases(9)), expect=10)
    assert check_skips.check(report(tmp_path, minio_cases(11)), expect=10)


def test_the_command_exits_non_zero_on_a_bad_report(tmp_path):
    assert check_skips.main([report(tmp_path, minio_cases(10)), "--expect", "10"]) == 0
    assert check_skips.main([report(tmp_path, [("a.b", "t", "Postgres is not reachable")])]) == 1
