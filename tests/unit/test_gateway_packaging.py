"""The runtime image copies packages one by one: the gateway package must be among them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_the_dockerfile_runtime_stage_copies_the_gateway_package():
    runtime = (ROOT / "Dockerfile").read_text().split("AS runtime", 1)[1]
    assert "COPY --from=builder /app/gateway gateway/" in runtime
    for package in ("api", "core"):
        assert f"COPY --from=builder /app/{package} {package}/" in runtime


def test_ci_lints_and_typechecks_the_gateway_package():
    assert "ruff check api/ core/ gateway/ tests/" in (ROOT / ".github" / "workflows" / "tests.yml").read_text()
    assert '"gateway"' in (ROOT / "pyproject.toml").read_text().split("[tool.mypy]", 1)[1].split("\n", 3)[2]


def test_the_limits_module_uses_the_same_api_prefix_as_the_app():
    from api.versioning import API_PREFIX
    from gateway.limits import API_PREFIX as GATEWAY_PREFIX

    assert GATEWAY_PREFIX == API_PREFIX
