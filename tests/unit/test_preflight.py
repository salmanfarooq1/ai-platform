"""Exercise runtime, resource, clock and port failures with deterministic command stubs."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_preflight(tmp_path, **overrides):
    commands = {
        "docker": '''#!/bin/sh
case "$1" in
info) [ "${BAD_ENGINE:-0}" = 0 ] || exit 1; echo "${ENGINE_OS:-Linux}" ;;
run) echo "${CONTAINER_TIME:-1000}" ;;
ps) [ "${OWNED_PORT:-0}" = 0 ] || echo container-id ;;
volume) [ "${EXISTING_VOLUMES:-}" = "" ] || printf '%s\n' "$EXISTING_VOLUMES" ;;
port) printf '5432/tcp -> 127.0.0.1:5432\n6379/tcp -> 127.0.0.1:6379\n8000/tcp -> 127.0.0.1:8000\n5173/tcp -> 127.0.0.1:5173\n' ;;
esac
''',
        "date": "#!/bin/sh\necho 1000\n",
        "python3": '#!/bin/sh\n[ "${BUSY_PORT:-0}" = 0 ]\n',
    }
    commands["podman"] = commands["docker"].replace(
        'info) [', 'info) [ "$3" = "{{.Host.OS}}" ] || exit 2; ['
    )
    for name, source in commands.items():
        path = tmp_path / name
        path.write_text(source)
        path.chmod(0o755)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemAvailable: {overrides.pop('memory_kb', 16000000)} kB\n")
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "PREFLIGHT_MEMINFO": str(meminfo),
           "COMPOSE_PROFILES": "", "COMPOSE_PROJECT_NAME": "ai-platform", "PREFLIGHT_PORTS": "5432,6379,8000,5173", **overrides}
    return subprocess.run(["bash", str(ROOT / "scripts/preflight.sh")], env=env, text=True, capture_output=True)


def test_good_runtime_memory_clock_and_free_ports(tmp_path):
    result = run_preflight(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clocks agree" in result.stdout and "Port 5173 is free" in result.stdout


@pytest.mark.parametrize("settings, message", [
    ({"BAD_ENGINE": "1"}, "engine is unavailable"),
    ({"memory_kb": 1024}, "Insufficient available memory"),
    ({"CONTAINER_TIME": "990"}, "clock skew"),
    ({"BUSY_PORT": "1"}, "occupied outside Compose project"),
    ({"COMPOSE_PROFILES": "unknown"}, "Unknown preflight profile"),
    ({"PREFLIGHT_PORTS": "0"}, "Invalid preflight port"),
])
def test_failed_check_fails_closed(tmp_path, settings, message):
    result = run_preflight(tmp_path, **settings)
    assert result.returncode == 1
    assert message in result.stdout + result.stderr


def test_existing_project_container_is_allowed(tmp_path):
    result = run_preflight(tmp_path, BUSY_PORT="1", OWNED_PORT="1")
    assert result.returncode == 0 and "belongs to Compose project" in result.stdout


def test_podman_uses_its_info_schema_and_project_port_mapping(tmp_path):
    result = run_preflight(tmp_path, CONTAINER_ENGINE="podman", BUSY_PORT="1", OWNED_PORT="1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Engine reachable: podman" in result.stdout and "belongs to Compose project" in result.stdout


def test_desktop_is_reported_and_profiles_add_memory(tmp_path):
    result = run_preflight(tmp_path, ENGINE_OS="Docker Desktop", COMPOSE_PROFILES="models,lake,streams,observability")
    assert result.returncode == 0
    assert "Docker Desktop detected" in result.stdout and "10036 MiB" in result.stdout


def test_old_renamed_volume_prints_warning_without_failing(tmp_path):
    result = run_preflight(tmp_path, EXISTING_VOLUMES="ai-platform_pgdata")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Warning: old volume ai-platform_pgdata exists" in result.stdout
    assert "replacement ai-platform_pgdata_trixie does not" in result.stdout


@pytest.mark.parametrize("profile,ports", [("streams", "19092"), ("lake", "8333"),
                                           ("models", "11434"), ("observability", "9090,3000")])
def test_selected_profile_ports_are_checked(tmp_path, profile, ports):
    result = run_preflight(tmp_path, COMPOSE_PROFILES=profile)
    assert result.returncode == 0, result.stdout + result.stderr
    for port in ports.split(","):
        assert f"Port {port} is free" in result.stdout
