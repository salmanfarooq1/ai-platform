"""The runtime image copies packages one by one: the gateway package must be among them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_the_dockerfile_runtime_stage_copies_the_gateway_package():
    runtime = (ROOT / "Dockerfile").read_text().split("AS runtime", 1)[1]
    assert "COPY --from=builder /app/gateway gateway/" in runtime
    for package in ("api", "core", "ports", "adapters", "workers"):  # ports and adapters: Sprint 006; workers: Sprint 007
        assert f"COPY --from=builder /app/{package} {package}/" in runtime


def test_ci_lints_and_typechecks_the_gateway_package():
    assert "ruff check api core gateway ports adapters workers tests scripts/e2e" in (ROOT / ".github" / "workflows" / "tests.yml").read_text()
    mypy_files = (ROOT / "pyproject.toml").read_text().split("[tool.mypy]", 1)[1].split("\n", 3)[2]
    assert '"gateway"' in mypy_files and '"ports"' in mypy_files and '"adapters"' in mypy_files and '"workers"' in mypy_files


def test_the_limits_module_uses_the_same_api_prefix_as_the_app():
    from api.versioning import API_PREFIX
    from gateway.limits import API_PREFIX as GATEWAY_PREFIX

    assert GATEWAY_PREFIX == API_PREFIX


def test_the_compose_file_has_a_worker_service_running_the_same_image_with_the_worker_command():
    compose = (ROOT / "docker-compose.yml").read_text()
    worker = compose.split("  worker:", 1)[1].split("\n  ollama:", 1)[0]
    assert "build: ." in worker and '"python", "-m", "workers"' in worker and "healthcheck" in worker
