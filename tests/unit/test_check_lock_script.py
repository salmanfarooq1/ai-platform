import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class TagsHandler(BaseHTTPRequestHandler):
    payload: dict[str, object] = {"models": []}

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(type(self).payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_check_lock_detects_mismatch(tmp_path: Path) -> None:
    digest = "a" * 64
    lock = tmp_path / "models.lock"
    lock.write_text(
        'version=1\n[[model]]\nalias="ollama/example"\nruntime="ollama"\n'
        f'digest="sha256:{digest}"\nlicence="Apache-2.0"\n'
        'source="https://example.org/model"\nsize_bytes=1\nuse=["chat"]\n',
        encoding="utf-8",
    )
    server = HTTPServer(("127.0.0.1", 0), TagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = {"MODEL_LOCK": str(lock), "OLLAMA_URL": f"http://127.0.0.1:{server.server_port}"}
    try:
        TagsHandler.payload = {"models": [{"name": "example", "digest": digest}]}
        matched = subprocess.run(["scripts/models/check_lock.sh"], env={**os.environ, **environment}, capture_output=True, text=True)
        assert matched.returncode == 0, matched.stderr

        TagsHandler.payload = {"models": [{"name": "example", "digest": "b" * 64}]}
        mismatch = subprocess.run(["scripts/models/check_lock.sh"], env={**os.environ, **environment}, capture_output=True, text=True)
        assert mismatch.returncode == 1
        assert "ollama/example" in mismatch.stderr

        TagsHandler.payload = {"models": []}
        missing = subprocess.run(["scripts/models/check_lock.sh"], env={**os.environ, **environment}, capture_output=True, text=True)
        assert missing.returncode == 1
        assert "ollama/example" in missing.stderr
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
