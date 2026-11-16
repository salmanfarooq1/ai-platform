"""Review regressions for lock observation and the shell entry point."""
import os
import subprocess
from unittest.mock import MagicMock

import pytest

from tests.integration.refco import test_policy_cas
from tests.unit.refco.test_public_seams import ROOT


def test_wait_for_lock_observes_backend_before_returning():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [(None,), ("Lock",)]
    test_policy_cas.wait_for_lock(conn, 123, timeout=1)
    assert cursor.execute.call_count == 2
    assert all(call.args[1] == (123,) for call in cursor.execute.call_args_list)
    assert "pg_stat_activity" in cursor.execute.call_args.args[0]


def test_wait_for_lock_timeout_fails():
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ("Client",)
    with pytest.raises(AssertionError, match="lock"):
        test_policy_cas.wait_for_lock(conn, 123, timeout=0)


@pytest.mark.parametrize("runner", ["poetry", "override", "missing"])
def test_m0_shell_resolves_runner(tmp_path, runner):
    (tmp_path / "dirname").symlink_to("/usr/bin/dirname")
    shim = tmp_path / ("poetry" if runner == "poetry" else "python-override")
    if runner != "missing":
        shim.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        shim.chmod(0o700)
    env = dict(os.environ, PATH=str(tmp_path))
    env.pop("SHOWCASE_PYTHON", None)
    if runner == "override":
        env["SHOWCASE_PYTHON"] = str(shim)
    result = subprocess.run(["/bin/bash", str(ROOT / "scripts/showcase/m0.sh"), "--help"],
                            env=env, capture_output=True, text=True, timeout=10)
    if runner == "missing":
        assert result.returncode != 0
        assert "poetry on PATH" in result.stderr and "SHOWCASE_PYTHON" in result.stderr
    else:
        assert result.returncode == 0
        expected = ["-m", "scripts.showcase.m0", "--help"]
        assert result.stdout.splitlines() == (["run", "python", *expected] if runner == "poetry" else expected)
