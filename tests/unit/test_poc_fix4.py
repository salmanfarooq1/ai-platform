"""Regressions for lifecycle locking and generated contracts."""
import fcntl
import os
from pathlib import Path

import pytest

from api.models.jobs import Job
from scripts.poc_lib import lifecycle
from scripts.poc_lib.up import PocError, compose_env


def test_held_lock_refuses_before_context_load(tmp_path, monkeypatch):
    stack_dir = tmp_path / '.poc' / 'example'
    lock_dir = stack_dir.parent / '.locks'
    stack_dir.parent.mkdir(mode=0o700)
    lock_dir.mkdir(mode=0o700)
    fd = os.open(lock_dir / 'example.lock', os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    def forbidden(*args, **kwargs):
        raise AssertionError('context must not load before lock')
    monkeypatch.setattr(lifecycle, 'load_context', forbidden)
    try:
        for action in (lifecycle.backup, lifecycle.down):
            with pytest.raises(PocError, match='another'):
                action(tmp_path, 'example')
    finally:
        os.close(fd)


def test_job_deferrals_required_in_schema():
    assert 'deferrals' in Job.model_json_schema()['required']


def test_compose_env_rejects_invalid_operator_url():
    with pytest.raises(PocError, match='POC_OLLAMA_BASE_URL'):
        compose_env({'POC_OLLAMA_BASE_URL': 'file:///bad'}, {'api_port': 8000})


def test_accept_uses_poetry_interpreter_for_showcase():
    source = Path('planning/sprints/015-local-poc-lifecycle/accept.sh').read_text()
    assert 'SHOWCASE_PYTHON=' in source and 'sys.executable' in source


def test_showcase_missing_dependency_has_clear_error():
    import subprocess
    result = subprocess.run(['bash', 'scripts/showcase/m0.sh', 'example'],
                            env={'PATH': '/usr/bin:/bin', 'SHOWCASE_PYTHON': '/usr/bin/python3'},
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert 'FAIL m0:' in result.stderr and 'dependencies' in result.stderr


def test_drill_missing_dependency_has_clear_error():
    import subprocess
    result = subprocess.run(['bash', 'scripts/verify/poc-drill.sh', 'example'],
                            env={'PATH': '/usr/bin:/bin', 'SHOWCASE_PYTHON': '/usr/bin/python3'},
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert 'FAIL prerequisites:' in result.stdout and 'dependencies' in result.stdout
