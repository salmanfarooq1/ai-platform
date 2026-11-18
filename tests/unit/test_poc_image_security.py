"""Security contract for locally built backup and application images."""
import re
import subprocess
from pathlib import Path
from unittest.mock import Mock

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_restic_build_security():
    text = (ROOT / 'docker/restic/Dockerfile').read_text()
    match = re.search(r'FROM golang:(\d+)\.(\d+)\.(\d+)-alpine3\.24@sha256:([a-f0-9]{64})', text)
    assert match and tuple(map(int, match.group(1, 2, 3))) >= (1, 26, 9)
    assert re.search(r'\b[a-f0-9]{64}\s+\s*restic-0\.19\.1\.tar\.gz', text)
    match = re.search(r'golang.org/x/net@v(\d+)\.(\d+)\.(\d+)', text)
    assert match and tuple(map(int, match.groups())) >= (0, 60, 0)
    assert 'CGO_ENABLED=0' in text and 'FROM scratch' in text
    assert re.search(r'(?m)^USER\s+\d+(?::\d+)?$', text)


def test_restic_compose_security():
    service = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())['services']['restic']
    assert service['build']['context'] == 'docker/restic'
    assert service['network_mode'] == 'none' and service['read_only'] is True
    assert service['cap_drop'] == ['ALL']


def test_no_old_python_pins():
    files = subprocess.check_output(['git', 'grep', '-l', '3.11.' + '17-slim', '--', ':!planning/sprints/*/evidence/*'], cwd=ROOT, text=True).splitlines() if subprocess.run(['git', 'grep', '-q', '3.11.' + '17-slim', '--', ':!planning/sprints/*/evidence/*'], cwd=ROOT).returncode == 0 else []
    assert not files, files


def test_restic_builds_only_when_missing(tmp_path):
    from scripts.poc_backup.restic import Restic
    context = Mock()
    context.stack_dir = tmp_path
    context.compose.return_value.returncode = 0
    Restic(context).run('version')
    calls = context.compose.call_args_list
    assert calls[0].args == ('run', '--rm', '--no-deps', '-T', 'restic', 'version')
    assert '--build' not in calls[0].args
    assert calls[0].kwargs['profile'] == 'backup'
    # Compose run must build a missing local image automatically, without pulling.
    assert calls[0].kwargs.get('check', True) is True
