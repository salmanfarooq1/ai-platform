"""Sprint 013 A4, spec row 8.2: the live digest-binding check against a local Ollama.

It sends a real model request to a local runtime, so it lives in the live tier (`pytest -m live`): the unit tier has
no external dependencies and CI has no Ollama. It skips when Ollama is not reachable.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def test_live_digest_check_is_conditional():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2):
            pass
    except (OSError, urllib.error.URLError):
        pytest.skip("Ollama is not available; digest binding is checked when the local runtime is present")

    import tomllib

    with (ROOT / "models.lock").open("rb") as stream:
        lock = tomllib.load(stream)
    model = next(item for item in lock["model"] if "chat" in item["use"])
    request = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps({"model": model["digest"], "messages": [{"role": "user", "content": "Reply with ok."}],
                         # Bounded context: the 8192 default KV cache does not fit a 4 GB dev VM.
                         "stream": False, "options": {"num_ctx": 2048}}).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        assert response.status == 200
        payload = json.load(response)
    assert payload.get("message", {}).get("content")
