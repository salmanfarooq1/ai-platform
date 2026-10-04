"""The UI's nginx template adds the preview key server-side (requirement 10); nothing bakes it into the build."""
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "ui" / "nginx.conf").read_text()


def envsubst(template: str, env: dict[str, str]) -> str:
    """What the nginx image's envsubst step does: replace ${VAR} only for variables that are defined."""
    return re.sub(r"\$\{(\w+)\}", lambda m: env[m.group(1)] if m.group(1) in env else m.group(0), template)


def test_template_sets_the_authorization_header_from_the_environment_on_api_calls_only():
    api_block = re.search(r"location /api/ \{(.*?)\n    \}", TEMPLATE, re.S).group(1)
    assert 'proxy_set_header Authorization "Bearer ${PREVIEW_API_KEY}";' in api_block
    assert TEMPLATE.count("PREVIEW_API_KEY}") == 1
    assert "Authorization" not in TEMPLATE.split("location / {")[1]  # not on static files


def test_rendered_config_carries_the_value_and_leaves_nginx_variables_alone():
    rendered = envsubst(TEMPLATE, {"PREVIEW_API_KEY": "gap_abcd1234_" + "x" * 43})
    assert 'proxy_set_header Authorization "Bearer gap_abcd1234_' in rendered
    assert "${" not in rendered
    for nginx_var in ("$remote_addr", "$proxy_add_x_forwarded_for", "$scheme", "$uri"):
        assert nginx_var in rendered


def test_no_real_key_is_committed_in_the_template_or_the_dockerfile():
    for name in ("nginx.conf", "Dockerfile.ui", "vite.config.js"):
        assert not re.search(r"gap_[a-z0-9]{8}_[A-Za-z0-9_-]{32,}", (ROOT / "ui" / name).read_text()), name


def test_dockerfile_renders_the_template_at_runtime_not_build_time():
    dockerfile = (ROOT / "ui" / "Dockerfile.ui").read_text()
    assert "/etc/nginx/templates/default.conf.template" in dockerfile
    assert "PREVIEW_API_KEY" not in re.sub(r"#.*", "", dockerfile).replace("docker-require-preview-key.sh", "")
    assert "ARG PREVIEW_API_KEY" not in dockerfile  # a build arg would end up in image layers


def run_guard(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", str(ROOT / "ui" / "docker-require-preview-key.sh")],
                          env={"PATH": os.environ["PATH"], **env}, capture_output=True, text=True)


def test_container_refuses_to_start_without_the_key_and_never_prints_it():
    missing = run_guard({})
    assert missing.returncode == 1 and "PREVIEW_API_KEY is not set" in missing.stderr
    assert run_guard({"PREVIEW_API_KEY": ""}).returncode == 1
    ok = run_guard({"PREVIEW_API_KEY": "gap_secretvalue"})
    assert ok.returncode == 0 and "gap_secretvalue" not in ok.stdout + ok.stderr


def test_render_blueprint_declares_the_secrets_as_unsynced():
    text = (ROOT / "render.yaml").read_text()
    for key in ("PREVIEW_API_KEY", "MIGRATION_DATABASE_URL", "DATABASE_URL"):
        assert re.search(rf"key: {key}\n\s+sync: false", text), key
