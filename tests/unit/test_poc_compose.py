"""WP1: the default local stack is four hardened services; the POC override isolates one stack per project."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SERVICES = {"postgres", "valkey", "api", "worker"}


class _Tagged:
    def __init__(self, tag, value):
        self.tag, self.value = tag, value


def _override_loader():
    """YAML loader that keeps the Compose `!reset` and `!override` tags instead of rejecting them."""
    class Loader(yaml.SafeLoader):
        pass

    def tagged(tag):
        def construct(loader, node):
            if isinstance(node, yaml.MappingNode):
                value = loader.construct_mapping(node, deep=True)
            elif isinstance(node, yaml.SequenceNode):
                value = loader.construct_sequence(node, deep=True)
            else:
                value = loader.construct_scalar(node)
            return _Tagged(tag, value)
        return construct

    Loader.add_constructor("!reset", tagged("reset"))
    Loader.add_constructor("!override", tagged("override"))
    return Loader


def _compose_json(*files, env=None, project="ai-platform-poc-unit"):
    command = ["docker", "compose", "-p", project, "--env-file", "/dev/null"]
    for file in files:
        command += ["-f", str(ROOT / file)]
    command += ["config", "--format", "json"]
    import os
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                            env={**os.environ, "COMPOSE_PROFILES": "", **(env or {})})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _default_services(compose):
    return {name: svc for name, svc in compose["services"].items() if not svc.get("profiles")}


def test_default_services_and_hardening():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    default = _default_services(compose)
    assert set(default) == DEFAULT_SERVICES
    api, worker = default["api"], default["worker"]
    # One shared artifact: the same Dockerfile and context build both processes.
    assert api["build"] == worker["build"] == "."
    assert "image" not in api and "image" not in worker
    assert api["command"][:2] == ["uvicorn", "api.main:app"]
    assert worker["command"][:3] == ["python", "-m", "workers"]
    for service in (api, worker):
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["healthcheck"]["test"]
        assert service["environment"]["EMBEDDED_WORKERS"] == "0"
        assert service["environment"]["DATABASE_URL"].startswith("postgresql://gap_app:")
        # Only the object store and temp-file volumes and the small tmpfs are writable; everything else is the read-only root.
        assert service["volumes"] == ["objects:/data/objects", "app_tmp:/var/tmp/app"]
        assert len(service["tmpfs"]) == 1 and service["tmpfs"][0].startswith("/tmp")
        assert not service.get("privileged") and "network_mode" not in service
    # The API is loopback only; nothing else of the default set publishes by default except the two
    # existing local database ports that are also loopback bound.
    assert api["ports"] == ["127.0.0.1:${API_HOST_PORT:-8000}:8000"]
    for name, service in default.items():
        for port in service.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), name
    # The rendered default set is exactly the four services with healthchecks.
    rendered = _compose_json("docker-compose.yml")
    assert set(_default_services(rendered)) == DEFAULT_SERVICES
    for name in DEFAULT_SERVICES:
        assert rendered["services"][name]["healthcheck"]["test"], name
    for name in ("api", "worker"):
        assert rendered["services"][name]["read_only"] is True
        assert rendered["services"][name]["cap_drop"] == ["ALL"]
    # This harness sets COMPOSE_PROFILES empty itself, so it shows the default set is profile-free. That `poc up`
    # ignores an ambient COMPOSE_PROFILES is asserted in test_poc_up.py (compose_env) and the live test.
    ambient = _compose_json("docker-compose.yml", env={"COMPOSE_PROFILES": ""})
    assert set(ambient["services"]) == DEFAULT_SERVICES


def test_poc_override_resets_names_and_ports():
    override = yaml.load((ROOT / "docker/poc.override.yml").read_text(), Loader=_override_loader())["services"]
    for name in ("postgres", "worker"):
        assert override[name]["container_name"].tag == "reset"
    for name in ("postgres", "valkey"):
        assert override[name]["ports"].tag == "reset"
    api_ports = override["api"]["ports"]
    assert api_ports.tag == "override" and api_ports.value == ["127.0.0.1:${POC_API_PORT:?set by poc up}:8000"]
    rendered = _compose_json("docker-compose.yml", "docker/poc.override.yml", env={"POC_API_PORT": "18123"})
    services = rendered["services"]
    assert set(services) == DEFAULT_SERVICES
    assert all("container_name" not in service for service in services.values())
    published = {name: svc.get("ports") for name, svc in services.items() if svc.get("ports")}
    assert list(published) == ["api"]
    (port,) = published["api"]
    assert port["host_ip"] == "127.0.0.1" and str(port["published"]) == "18123" and port["target"] == 8000
    # The stack takes no developer environment files and runs as the host user so the key mount is readable.
    for name in ("api", "worker"):
        assert "env_file" not in services[name]
    assert rendered["name"] == "ai-platform-poc-unit"
    for volume in rendered["volumes"].values():
        assert volume["name"].startswith("ai-platform-poc-unit_")


@pytest.mark.parametrize("missing", ["POC_API_PORT"])
def test_poc_override_requires_its_port(missing):
    command = ["docker", "compose", "--env-file", "/dev/null", "-f", "docker-compose.yml",
               "-f", "docker/poc.override.yml", "config", "--quiet"]
    import os
    env = {k: v for k, v in os.environ.items() if k != missing}
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
    assert result.returncode != 0


def test_api_host_port_is_configurable_and_loopback_bound():
    default = _compose_json("docker-compose.yml")["services"]["api"]["ports"]
    (port,) = default
    assert port["host_ip"] == "127.0.0.1" and str(port["published"]) == "8000" and port["target"] == 8000
    custom = _compose_json("docker-compose.yml", env={"API_HOST_PORT": "18080"})["services"]["api"]["ports"]
    (port,) = custom
    assert port["host_ip"] == "127.0.0.1" and str(port["published"]) == "18080"


def test_temp_files_live_on_a_volume_not_on_the_small_tmpfs():
    services = _compose_json("docker-compose.yml")["services"]
    for name in ("api", "worker"):
        service = services[name]
        assert service["environment"]["TMPDIR"] == "/var/tmp/app"
        targets = {v["target"]: v for v in service["volumes"]}
        assert targets["/var/tmp/app"]["type"] == "volume" and targets["/var/tmp/app"]["source"] == "app_tmp"
        assert all(not t["target"].startswith("/var/tmp") for t in service.get("tmpfs", []) if isinstance(t, dict))
        tmpfs = service["tmpfs"]
        assert [str(t) for t in tmpfs if "/var/tmp" in str(t)] == []
        assert any(str(t).startswith("/tmp") for t in tmpfs)
    assert "app_tmp" in _compose_json("docker-compose.yml")["volumes"]


def test_bootstrap_keeps_the_password_out_of_argv():
    text = (ROOT / "docker/poc-bootstrap.sh").read_text()
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not any("pw=" in line and "psql" in line for line in code), "password must not be a psql argument"
    assert "PGPASSWORD" not in text or "-v pw" not in text


def test_a_poc_stack_can_point_at_a_model_runtime_on_the_host():
    """`POC_OLLAMA_BASE_URL` reaches the API and the worker as `OLLAMA_BASE_URL`; the default is the old loopback value."""
    default = _compose_json("docker-compose.yml", "docker/poc.override.yml", env={"POC_API_PORT": "18123"})["services"]
    custom = _compose_json("docker-compose.yml", "docker/poc.override.yml",
                           env={"POC_API_PORT": "18123", "POC_OLLAMA_BASE_URL": "http://host.docker.internal:4321"})["services"]
    for name in ("api", "worker"):
        assert default[name]["environment"]["OLLAMA_BASE_URL"] == "http://127.0.0.1:11434"
        assert custom[name]["environment"]["OLLAMA_BASE_URL"] == "http://host.docker.internal:4321"
        assert any(str(host).startswith("host.docker.internal") for host in _hosts(custom[name]))
    for name in ("postgres", "valkey"):
        assert "OLLAMA_BASE_URL" not in (custom[name].get("environment") or {})


def _hosts(service):
    hosts = service.get("extra_hosts") or {}
    return list(hosts) if isinstance(hosts, dict) else hosts
