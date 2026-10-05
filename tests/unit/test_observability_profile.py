"""The `observability` compose profile (Sprint 008, A6): Prometheus and Grafana are optional, pinned, local only and
provisioned from files in the repo. `docker compose --profile observability config` is run as evidence (needs docker);
these tests read the files, so they run anywhere."""
import json
import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
OBS = ROOT / "docker" / "observability"


def test_prometheus_and_grafana_only_run_under_the_profile_with_pinned_images():
    for name in ("prometheus", "grafana"):
        service = COMPOSE["services"][name]
        assert service["profiles"] == ["observability"], name
        image = service["image"]
        assert re.search(r":v?\d+\.\d+\.\d+$", image), f"{image} is not pinned to a version"
        assert "latest" not in image
        assert all(p.startswith("127.0.0.1:") for p in service["ports"]), "ports must bind to localhost only"
    # nothing else is behind the profile, and the core services are not
    assert all("profiles" not in COMPOSE["services"][n] for n in ("postgres", "redis", "worker"))


def test_prometheus_scrapes_the_api_and_the_worker_and_holds_no_credential():
    text = (OBS / "prometheus.yml").read_text()
    config = yaml.safe_load(text)
    jobs = {j["job_name"]: j for j in config["scrape_configs"]}
    assert set(jobs) == {"api", "worker"} and all(j["metrics_path"] == "/metrics" for j in jobs.values())
    assert COMPOSE["services"]["worker"]["environment"]["WORKER_METRICS_PORT"] == "9100"
    assert "worker:9100" in jobs["worker"]["static_configs"][0]["targets"]
    assert "credentials:" not in text and "password" not in text.lower()  # a token goes in a file the operator mounts


def test_the_provisioned_dashboard_charts_every_listed_series():
    dashboard = json.loads((OBS / "grafana" / "dashboards" / "platform.json").read_text())
    expressions = " ".join(t["expr"] for p in dashboard["panels"] for t in p["targets"])
    for series in ("http_requests_total", "http_request_duration_seconds_bucket", "gateway_decisions_total", "jobs_total", "outbox_lag_seconds"):
        assert series in expressions, series
    assert dashboard["uid"] == "platform-trust" and dashboard["editable"] is False
    datasource = yaml.safe_load((OBS / "grafana" / "provisioning" / "datasources" / "prometheus.yml").read_text())["datasources"][0]
    assert datasource["uid"] == "prometheus" and datasource["url"] == "http://prometheus:9090"
    providers = yaml.safe_load((OBS / "grafana" / "provisioning" / "dashboards" / "dashboards.yml").read_text())["providers"]
    assert providers[0]["options"]["path"] == "/var/lib/grafana/dashboards"
    mounts = COMPOSE["services"]["grafana"]["volumes"]
    assert any(m.endswith(":/var/lib/grafana/dashboards:ro") for m in mounts) and any(m.endswith(":/etc/grafana/provisioning:ro") for m in mounts)
