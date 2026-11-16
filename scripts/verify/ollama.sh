#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
project=ai-platform
failed=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'PASS: %s\n' "$label"
  else
    printf 'FAIL: %s\n' "$label"
    failed=1
  fi
}

network_is_isolated() {
  local details
  details="$(docker inspect ollama)" || return 1
  python3 -c '
import json, sys
container = json.load(sys.stdin)[0]
attached = container["NetworkSettings"]["Networks"]
if list(attached) != ["ai-platform_models_internal"]:
    raise SystemExit(1)
network = json.loads(__import__("subprocess").check_output(
    ["docker", "network", "inspect", "ai-platform_models_internal"], text=True
))[0]
if network.get("Internal") is not True:
    raise SystemExit(1)
' <<<"$details"
}

no_published_ports() {
  docker inspect ollama | python3 -c '
import json, sys
container = json.load(sys.stdin)[0]
if container["HostConfig"].get("PortBindings") not in ({}, None):
    raise SystemExit(1)
if any(value for value in container["NetworkSettings"].get("Ports", {}).values() if value):
    raise SystemExit(1)
'
}

blocked_from_network() {
  docker exec ollama bash -c 'timeout 5 bash -c "</dev/tcp/1.1.1.1/443"' >/dev/null 2>&1 && return 1
  docker exec ollama bash -c 'timeout 5 bash -c "</dev/tcp/registry.ollama.ai/443"' >/dev/null 2>&1 && return 1
  return 0
}

host_can_reach_all_locked_models() {
  python3 - <<'PY'
import json
import tomllib
import urllib.request

with open("models.lock", "rb") as stream:
    lock = tomllib.load(stream)
with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
    if response.status != 200:
        raise SystemExit(1)
    tags = json.load(response)
available = {item.get("name") for item in tags.get("models", [])}
required = {
    item["alias"].removeprefix("ollama/")
    for item in lock.get("model", [])
    if item.get("runtime") == "ollama"
}
if not required or not required <= available:
    raise SystemExit(1)
PY
}

lock_check_succeeded() {
  local container_id
  container_id="$(docker compose -p "$project" --profile models ps -aq ollama-lock-check)" || return 1
  [[ -n "$container_id" ]] || return 1
  docker inspect "$container_id" | python3 -c '
import json, sys
state = json.load(sys.stdin)[0]["State"]
if state.get("Status") != "exited" or state.get("ExitCode") != 0:
    raise SystemExit(1)
'
}

serving_store_is_read_only() {
  if docker exec ollama touch /root/.ollama/x >/dev/null 2>&1; then
    docker exec ollama rm -f /root/.ollama/x >/dev/null 2>&1 || true
    return 1
  fi
  return 0
}

check "Ollama is attached only to the internal models network" network_is_isolated
check "Ollama has no published ports" no_published_ports
check "Ollama cannot reach external IP or DNS endpoints" blocked_from_network
check "host endpoint returns all models in models.lock" host_can_reach_all_locked_models
check "ollama-lock-check exited successfully" lock_check_succeeded
check "Ollama model store is read-only" serving_store_is_read_only

exit "$failed"
