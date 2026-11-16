#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
exec python3 - "$@" <<'PY'
import json
import os
import sys
import tomllib
import urllib.error
import urllib.request

lock_path = os.environ.get("MODEL_LOCK", "models.lock")
endpoint = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
try:
    with open(lock_path, "rb") as lock_file:
        lock = tomllib.load(lock_file)
    with urllib.request.urlopen(endpoint + "/api/tags", timeout=5) as response:
        tags_payload = json.load(response)
except (OSError, urllib.error.URLError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
    print(f"model lock check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(1)

actual = {
    item.get("name"): "sha256:" + str(item.get("digest", "")).removeprefix("sha256:")
    for item in tags_payload.get("models", [])
    if isinstance(item, dict) and isinstance(item.get("name"), str)
}
failed = False
for model in lock.get("model", []):
    if model.get("runtime") != "ollama":
        continue
    alias = str(model.get("alias", ""))
    name = alias.removeprefix("ollama/")
    locked = model.get("digest")
    found = actual.get(name)
    if found is None:
        print(f"missing locked model: {alias}", file=sys.stderr)
        failed = True
    elif found != locked:
        print(f"digest mismatch for {alias}: lock {locked}, Ollama {found}", file=sys.stderr)
        failed = True
if failed:
    raise SystemExit(1)
print(f"model lock ok: {sum(model.get('runtime') == 'ollama' for model in lock.get('model', []))} Ollama models match")
PY
