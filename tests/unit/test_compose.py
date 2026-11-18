"""Check the final local stack's published interfaces and optional profiles."""
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

ONE_SHOT_SERVICES = {
    "ollama-init": "populates the model store",
    "ollama-lock-check": "verifies model digests before exposing the endpoint",
    "kafka-topics": "creates Kafka topics",
    "seaweedfs-init": "initializes the object store",
    "restic": "a one-off `run --rm` tool of the `backup` profile (Sprint 015): runs to completion per command, never restarts",
}

# Long-running services without a probe. Each needs a reason, and no service may wait on it.
NO_PROBE_SERVICES = {
    "grafana": "distroless image has no shell or HTTP client to probe with; dashboards only, nothing depends on it",
}


@pytest.mark.parametrize("profile", ["", "models", "streams", "lake", "observability"])
def test_compose_profiles_render_with_loopback_ports(profile):
    command = ["docker", "compose", *(["--profile", profile] if profile else []), "config", "--format", "json"]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    for service in config["services"].values():
        for port in service.get("ports", []):
            assert port.get("host_ip") == "127.0.0.1"
    if not profile:
        assert set(config["services"]) == {"postgres", "valkey", "api", "worker"}


def test_images_health_dependencies_and_preserved_old_volumes():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name, service in compose["services"].items():
        if "image" in service:
            assert re.fullmatch(r"[^@]+:[^@]+@sha256:[0-9a-f]{64}", service["image"])
        if name in ONE_SHOT_SERVICES:
            assert service.get("restart") == "no"
        elif name in NO_PROBE_SERVICES:
            assert service.get("profiles"), name
            assert not any(name in other.get("depends_on", {}) for other in compose["services"].values()), name
        else:
            assert service.get("healthcheck"), name
    assert {"pgdata", "pgdata_trixie", "redis_data", "valkey_data"} <= compose["volumes"].keys()
    assert {"grafana_data", "grafana_data_v13"} <= compose["volumes"].keys()
    assert "grafana_data:/var/lib/grafana" not in compose["services"]["grafana"]["volumes"]
    assert "redis_data:/data" not in compose["services"]["valkey"]["volumes"]
    assert "pgdata:/var/lib/postgresql/data" not in compose["services"]["postgres"]["volumes"]
    assert compose["services"]["worker"]["environment"]["REDIS_URL"] == "redis://valkey:6379"


def test_dependencies_wait_for_healthy_services_or_one_shot_jobs():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for name, service in compose["services"].items():
        for dependency_name, dependency in service.get("depends_on", {}).items():
            expected = "service_completed_successfully" if dependency_name in ONE_SHOT_SERVICES else "service_healthy"
            assert dependency["condition"] == expected, (name, dependency_name)


def test_ollama_serves_read_only_store():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    service = compose["services"]["ollama"]
    initializer = compose["services"]["ollama-init"]
    assert "ollama_data_v0407:/root/.ollama:ro" in service["volumes"]
    assert "ollama_data_v0407:/root/.ollama" in initializer["volumes"]
    assert "ports" not in service
    command = initializer["command"][0]
    assert all(alias in command for alias in ("qwen3:4b-instruct-2507-q4_K_M", "qwen3:1.7b", "nomic-embed-text:v1.5"))
    assert "check_lock.sh" not in command
    assert "./models.lock:/app/models.lock:ro" not in initializer["volumes"]
    assert "./scripts/models/check_lock.sh:/scripts/check_lock.sh:ro" not in initializer["volumes"]
    digest = r"[^@]+:[^@]+@sha256:[0-9a-f]{64}"
    assert re.fullmatch(digest, service["image"])
    assert re.fullmatch(digest, initializer["image"])
    assert service["environment"] == {
        "OLLAMA_NO_CLOUD": "1", "OLLAMA_NOPRUNE": "1", "OLLAMA_MAX_LOADED_MODELS": "2",
        "OLLAMA_NUM_PARALLEL": "1", "OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_CONTEXT_LENGTH": "8192",
    }
    assert service["networks"] == ["models_internal"]
    assert compose["networks"]["models_internal"]["internal"] is True

    edge = compose["services"]["ollama-edge"]
    assert edge["build"] == {"context": "docker/socat"}
    assert "image" not in edge
    assert (ROOT / "docker/socat/Dockerfile").read_text().splitlines()[0] == "FROM alpine/socat:1.8.0.3@sha256:beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e"
    assert edge["command"] == ["TCP-LISTEN:11434,fork,reuseaddr", "TCP:ollama:11434"]
    assert edge["ports"] == ["127.0.0.1:11434:11434"]
    assert edge["networks"] == ["default", "models_internal"]
    assert edge["depends_on"]["ollama"]["condition"] == "service_healthy"
    assert edge["depends_on"]["ollama-lock-check"]["condition"] == "service_completed_successfully"
    assert edge["restart"] == "unless-stopped" and edge["read_only"] is True
    assert edge["cap_drop"] == ["ALL"] and edge["security_opt"] == ["no-new-privileges:true"]

    lock_check = compose["services"]["ollama-lock-check"]
    assert lock_check["image"] == "python:3.11.18-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39"
    assert re.fullmatch(digest, lock_check["image"])
    assert lock_check["command"] == ["/scripts/check_lock.sh"]
    assert lock_check["environment"] == {"MODEL_LOCK": "/app/models.lock", "OLLAMA_URL": "http://ollama:11434"}
    assert lock_check["volumes"] == ["./models.lock:/app/models.lock:ro", "./scripts/models/check_lock.sh:/scripts/check_lock.sh:ro"]
    assert lock_check["networks"] == ["models_internal"]
    assert lock_check["depends_on"]["ollama"]["condition"] == "service_healthy"
    assert lock_check["restart"] == "no"


def test_postgres_has_init_and_restart_policy():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    postgres = compose["services"]["postgres"]
    assert postgres["init"] is True
    assert postgres["restart"] == "unless-stopped"


def test_runtime_image_copies_evidence():
    dockerfile = (ROOT / "Dockerfile").read_text()
    runtime = dockerfile.split(" AS runtime", maxsplit=1)[1]
    assert re.search(r"^COPY --from=builder /app/evidence(?:/|\s)", runtime, re.MULTILINE)


def test_optional_security_services_use_digest_pinned_upstream_images():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    expected = {
        "ollama": "ollama/ollama:0.40.7@sha256:2e6cc92ffa43b4b1a2e70e315407e00ac97ec125afc71277d73c7efe01c4f31b",
        "ollama-init": "ollama/ollama:0.40.7@sha256:2e6cc92ffa43b4b1a2e70e315407e00ac97ec125afc71277d73c7efe01c4f31b",
        "seaweedfs": "chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882",
        "seaweedfs-init": "chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882",
    }
    for name, image in expected.items():
        service = compose["services"][name]
        assert service["image"] == image
        assert "build" not in service
    for name in ("kafka", "kafka-topics"):
        assert compose["services"][name]["build"] == {"context": "docker/kafka"}
        assert "image" not in compose["services"][name]
    assert (ROOT / "docker/kafka/Dockerfile").read_text().splitlines()[0] == "FROM apache/kafka:4.3.1@sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837"
    assert "./docker/seaweedfs/s3.json:/etc/seaweedfs/s3.json:ro" in compose["services"]["seaweedfs"]["volumes"]


def test_optional_init_jobs_keep_default_outbox_and_environment_credentials():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "EVENT_BUS" not in compose["services"]["worker"]["environment"]
    # Live tests create their own topics; kafka-topics still pre-creates the platform topics with 3 partitions.
    assert compose["services"]["kafka"]["environment"]["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "true"
    topic_job = compose["services"]["kafka-topics"]["command"][0]
    assert topic_job.index("--create --if-not-exists") < topic_job.index("--list")
    assert "retention.ms=604800000" in topic_job
    assert compose["services"]["ollama"]["volumes"] == ["ollama_data_v0407:/root/.ollama:ro"]
    init = compose["services"]["ollama-init"]
    assert "ollama pull" in init["command"][0] and "/scripts/check_lock.sh" not in init["command"][0]
    assert "ollama_data_v0407:/root/.ollama" in init["volumes"]
    assert "./models.lock:/app/models.lock:ro" not in init["volumes"]
    assert "./scripts/models/check_lock.sh:/scripts/check_lock.sh:ro" not in init["volumes"]
    assert "depends_on" not in init
    assert compose["services"]["ollama"]["depends_on"]["ollama-init"]["condition"] == "service_completed_successfully"
    assert compose["services"]["ollama"]["environment"]["OLLAMA_NO_CLOUD"] == "1"
    seaweed = compose["services"]["seaweedfs"]["environment"]
    for key in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        assert seaweed[key].startswith("${" + key + ":-")


def test_live_kafka_helper_creates_topics_before_contracts():
    script = (ROOT / "scripts/verify/kafka.sh").read_text()
    assert "docker compose --profile streams run --rm kafka-topics" in script
    assert script.index("run --rm kafka-topics") < script.index("poetry run pytest")
    assert " compose --profile streams build " not in script


def test_ollama_verifier_exists_is_executable_and_parses():
    script = ROOT / "scripts/verify/ollama.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
    result = subprocess.run(["bash", "-n", str(script)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
