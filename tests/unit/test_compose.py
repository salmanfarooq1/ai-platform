"""Check the final local stack's published interfaces and optional profiles."""
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


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
        assert set(config["services"]) == {"postgres", "valkey", "worker"}


def test_images_health_dependencies_and_preserved_old_volumes():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for service in compose["services"].values():
        if "image" in service:
            assert re.fullmatch(r"[^@]+:[^@]+@sha256:[0-9a-f]{64}", service["image"])
        assert service.get("profiles") or service.get("healthcheck")
        for dependency in service.get("depends_on", {}).values():
            assert dependency["condition"] == "service_healthy"
    assert {"pgdata", "pgdata_trixie", "redis_data", "valkey_data"} <= compose["volumes"].keys()
    assert {"grafana_data", "grafana_data_v13"} <= compose["volumes"].keys()
    assert "grafana_data:/var/lib/grafana" not in compose["services"]["grafana"]["volumes"]
    assert "redis_data:/data" not in compose["services"]["valkey"]["volumes"]
    assert "pgdata:/var/lib/postgresql/data" not in compose["services"]["postgres"]["volumes"]
    assert compose["services"]["worker"]["environment"]["REDIS_URL"] == "redis://valkey:6379"


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
        "kafka": "apache/kafka:4.3.1@sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837",
        "kafka-topics": "apache/kafka:4.3.1@sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837",
        "ollama": "ollama/ollama:0.40.7@sha256:2e6cc92ffa43b4b1a2e70e315407e00ac97ec125afc71277d73c7efe01c4f31b",
        "ollama-pull": "ollama/ollama:0.40.7@sha256:2e6cc92ffa43b4b1a2e70e315407e00ac97ec125afc71277d73c7efe01c4f31b",
        "seaweedfs": "chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882",
        "seaweedfs-init": "chrislusf/seaweedfs:4.47@sha256:ce9e796f1fe6f06968f4c04bdaf8f678dad9c8acdfef3d244133d71bfa6bf882",
    }
    for name, image in expected.items():
        service = compose["services"][name]
        assert service["image"] == image
        assert "build" not in service
    assert "./docker/seaweedfs/s3.json:/etc/seaweedfs/s3.json:ro" in compose["services"]["seaweedfs"]["volumes"]


def test_optional_init_jobs_keep_default_outbox_and_environment_credentials():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "EVENT_BUS" not in compose["services"]["worker"]["environment"]
    # Live tests create their own topics; kafka-topics still pre-creates the platform topics with 3 partitions.
    assert compose["services"]["kafka"]["environment"]["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "true"
    topic_job = compose["services"]["kafka-topics"]["command"][0]
    assert topic_job.index("--create --if-not-exists") < topic_job.index("--list")
    assert "retention.ms=604800000" in topic_job
    assert compose["services"]["ollama-pull"]["command"] == ["pull", "nomic-embed-text:v1.5"]
    seaweed = compose["services"]["seaweedfs"]["environment"]
    for key in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
        assert seaweed[key].startswith("${" + key + ":-")


def test_live_kafka_helper_creates_topics_before_contracts():
    script = (ROOT / "scripts/verify/kafka.sh").read_text()
    assert "docker compose --profile streams run --rm kafka-topics" in script
    assert script.index("run --rm kafka-topics") < script.index("poetry run pytest")
    assert " compose --profile streams build " not in script
