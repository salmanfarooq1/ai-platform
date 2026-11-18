import hashlib
from pathlib import Path

import pytest
import yaml

from scripts.poc_lib.runner import CommandError, Result
from scripts.release import build_manifest as bm
from scripts.supply_chain import check_pins

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize(("name", "user"), [("socat", "root"), ("kafka", "appuser")])
def test_patched_image(name, user):
    dockerfile = ROOT / "docker" / name / "Dockerfile"
    text = dockerfile.read_text()
    refs = list(check_pins.dockerfile_references(ROOT, dockerfile))
    assert len(refs) == 1 and check_pins.REFERENCE.fullmatch(refs[0][1])
    assert "RUN apk upgrade --no-cache" in text
    assert [line.split(maxsplit=1)[1] for line in text.splitlines() if line.startswith("USER ")][-1] == user
    assert "org.opencontainers.image.source" in text and "org.opencontainers.image.base.digest" in text


@pytest.mark.unit
def test_ui_patch_and_compose_images():
    assert "RUN apk upgrade --no-cache" in (ROOT / "ui/Dockerfile.ui").read_text().split("FROM nginx:")[-1]
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    for name, context, profile in (("ollama-edge", "socat", "models"), ("kafka", "kafka", "streams"),
                                   ("kafka-topics", "kafka", "streams")):
        service = services[name]
        assert service["build"]["context"] == f"docker/{context}"
        assert "image" not in service
        assert profile in service["profiles"]
        assert name in check_pins.built_services(ROOT)
    assert services["kafka"]["ports"] == ["127.0.0.1:19092:19092"]
    assert services["ollama-edge"]["cap_drop"] == ["ALL"]
    assert all("build" not in services[location.split(":")[-1]] for location, _ in check_pins.compose_references(ROOT))


@pytest.mark.unit
def test_registry_retries_command_failures():
    class Runner:
        calls = 0

        def run(self, argv):
            self.calls += 1
            if self.calls < 2:
                raise CommandError(argv, 1, b"temporary registry error")
            return Result(0, b"proof")

    runner = Runner()
    delays = []
    assert bm.registry_resolver(runner, sleep=delays.append)("example:1@sha256:" + "a" * 64) == b"proof"
    assert runner.calls == 2 and len(delays) == 1


@pytest.mark.unit
def test_registry_failure_reports_cause():
    class Runner:
        calls = 0

        def run(self, argv):
            self.calls += 1
            raise CommandError(argv, 1, b"temporary registry error")

    runner = Runner()
    with pytest.raises(bm.ManifestError, match="temporary registry error"):
        bm.registry_resolver(runner, sleep=lambda _: None)("example:1@sha256:" + "a" * 64)
    assert runner.calls == 3


@pytest.mark.unit
def test_registry_failure_reports_compose_location(monkeypatch, tmp_path):
    class Runner:
        def run(self, argv):
            raise CommandError(argv, 1, b"temporary registry error")

    monkeypatch.setattr(bm, "collect_inputs", lambda root: [{"location": "docker-compose.yml:grafana", "ref": "image"}])
    monkeypatch.setattr(bm, "local_identity", lambda images: {})
    with pytest.raises(bm.ManifestError, match="docker-compose.yml:grafana:.*temporary registry error"):
        bm.build_manifest(tmp_path, bm.registry_resolver(Runner(), sleep=lambda _: None), {},
                          platform="linux/amd64", source={})


@pytest.mark.unit
def test_registry_failure_redacts_sensitive_stderr():
    class Runner:
        def run(self, argv):
            raise CommandError(argv, 1, b"authorization: Bearer private-value")

    with pytest.raises(bm.ManifestError) as error:
        bm.registry_resolver(Runner(), sleep=lambda _: None)("image")
    assert "private-value" not in str(error.value)
    assert "redacted" in str(error.value)


@pytest.mark.unit
def test_bad_index_is_not_retried():
    class Runner:
        calls = 0

        def run(self, argv):
            self.calls += 1
            return Result(0, b"wrong")

    runner = Runner()
    ref = "example:1@sha256:" + hashlib.sha256(b"other").hexdigest()
    with pytest.raises(bm.ManifestError, match="do not match"):
        bm.verify_index(ref, bm.registry_resolver(runner, sleep=lambda _: None)(ref), "linux/amd64")
    assert runner.calls == 1


@pytest.mark.unit
def test_unpinned_dockerfile_base_is_detected(tmp_path):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM alpine:3.20\n")
    refs = list(check_pins.dockerfile_references(tmp_path, dockerfile))
    assert len(refs) == 1
    assert check_pins.REFERENCE.fullmatch(refs[0][1]) is None
