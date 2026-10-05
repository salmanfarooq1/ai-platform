"""The UI image serves the built app and proxies /v1. It holds no credential (Sprint 005, ADR-0007).

Before Sprint 005 these tests covered an nginx template that injected a preview API key. That mechanism is
removed (requirement 8), so they now check that it is gone and that the replacement adds no key.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX = (ROOT / "ui" / "nginx.conf").read_text()
DOCKERFILE = (ROOT / "ui" / "Dockerfile.ui").read_text()


def test_nginx_proxies_v1_without_adding_any_credential():
    v1_block = re.search(r"location /v1/ \{(.*?)\n    \}", NGINX, re.S)
    assert v1_block is not None
    assert "proxy_pass https://" in v1_block.group(1)
    assert "Authorization" not in NGINX
    assert "${" not in NGINX  # a static file, not an envsubst template
    assert "location /api/" not in NGINX  # the old key-injecting proxy path


def test_the_key_injection_files_and_names_are_gone():
    assert not (ROOT / "ui" / "docker-require-preview-key.sh").exists()
    for name in ("nginx.conf", "Dockerfile.ui", "vite.config.ts"):
        text = (ROOT / "ui" / name).read_text()
        assert "PREVIEW_API_KEY" not in text, name
        assert "/etc/nginx/templates" not in text, name


def test_no_real_key_is_committed_in_the_proxy_config_or_the_dockerfile():
    for name in ("nginx.conf", "Dockerfile.ui", "vite.config.ts"):
        assert not re.search(r"gap_[a-z0-9]{8}_[A-Za-z0-9_-]{32,}", (ROOT / "ui" / name).read_text()), name


def test_dockerfile_builds_the_typescript_app_and_serves_the_output():
    assert "npm ci" in DOCKERFILE
    assert "npm run build" in DOCKERFILE  # runs tsc --noEmit, then vite build
    assert "COPY --from=builder /app/dist /usr/share/nginx/html" in DOCKERFILE
    assert "/etc/nginx/conf.d/default.conf" in DOCKERFILE
    assert "ARG " not in DOCKERFILE  # no build arg can carry a secret into an image layer
    assert "npm run build" in (ROOT / "ui" / "package.json").read_text()


def test_render_blueprint_declares_the_secrets_as_unsynced_and_no_ui_key():
    text = (ROOT / "render.yaml").read_text()
    for key in ("PREVIEW_PRINCIPAL_ID", "MIGRATION_DATABASE_URL", "DATABASE_URL"):
        assert re.search(rf"key: {key}\n\s+sync: false", text), key
    assert "PREVIEW_API_KEY" not in text


def test_vite_dev_and_preview_proxy_forward_v1_and_add_no_credential():
    vite = (ROOT / "ui" / "vite.config.ts").read_text()
    assert "'/v1'" in vite
    assert "proxy" in vite and "preview:" in vite  # preview serves the e2e tests, so it proxies too
    assert "Authorization" not in vite and "headers" not in vite
    assert not (ROOT / "ui" / ".env.local").exists()  # the old dev proxy read the preview key from this file
