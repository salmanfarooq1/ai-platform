#!/usr/bin/env bash
# Local runtime readiness. Explicit port overrides support isolated development stacks.
set -euo pipefail
cd "$(dirname "$0")/.."
engine="${CONTAINER_ENGINE:-docker}"
case "$engine" in docker|podman) ;; *) echo "Unsupported CONTAINER_ENGINE: $engine" >&2; exit 1 ;; esac
command -v "$engine" >/dev/null || { echo "Container engine is missing" >&2; exit 1; }
info_format='{{.OperatingSystem}}'
[ "$engine" != podman ] || info_format='{{.Host.OS}}'
info=$("$engine" info --format "$info_format" 2>/dev/null) || { echo "Container engine is unavailable" >&2; exit 1; }
case "$info" in *[Dd]esktop*) echo "Warning: Docker Desktop detected; supported runtimes are Docker Engine (moby) or Podman." ;; esac
echo "Engine reachable: $engine"

# Core 2 GiB; optional budgets match planning/program/stack.md. Profiles are additive.
required_mb=2048
profiles="${COMPOSE_PROFILES:-}"
for profile in ${profiles//,/ }; do
    case "$profile" in
        core|"") ;;
        models) required_mb=$((required_mb + 4096)) ;;
        lake|streams) required_mb=$((required_mb + 1536)) ;;
        observability) required_mb=$((required_mb + 820)) ;;
        *) echo "Unknown preflight profile: $profile" >&2; exit 1 ;;
    esac
done
available_mb=$(awk '/^MemAvailable:/ {print int($2/1024)}' "${PREFLIGHT_MEMINFO:-/proc/meminfo}")
[[ "$available_mb" =~ ^[0-9]+$ ]] || { echo "Cannot determine available memory" >&2; exit 1; }
[ "$available_mb" -ge "$required_mb" ] || { echo "Insufficient available memory: ${available_mb} MiB; need ${required_mb} MiB" >&2; exit 1; }
echo "Memory available: ${available_mb} MiB; profile budget: ${required_mb} MiB"

clock_image=docker.io/valkey/valkey-bundle:9.1.3@sha256:dd30c59c2b2a598e83308095220a31d6d93d64c40a839c702cb1e98c8e220660
before=$(date +%s)
container_time=$("$engine" run --rm --network none --entrypoint date "$clock_image" +%s) || { echo "Container clock check failed" >&2; exit 1; }
after=$(date +%s)
[[ "$container_time" =~ ^[0-9]+$ ]] || { echo "Invalid container clock" >&2; exit 1; }
[ "$container_time" -ge "$((before - 5))" ] && [ "$container_time" -le "$((after + 5))" ] || { echo "Host/container clock skew exceeds 5 seconds" >&2; exit 1; }
echo "Host/container clocks agree"

# A port belongs to this stack only if its listening container carries this Compose project label.
project="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
volumes=$("$engine" volume ls --format '{{.Name}}')
for pair in pgdata:pgdata_trixie redis_data:valkey_data ollama_data:ollama_data_v0407 grafana_data:grafana_data_v13; do
    old="${pair%%:*}"
    new="${pair#*:}"
    old_name="${project}_${old}"
    new_name="${project}_${new}"
    if grep -Fxq "$old_name" <<< "$volumes" && ! grep -Fxq "$new_name" <<< "$volumes"; then
        echo "Warning: old volume $old_name exists and replacement $new_name does not; back up and restore data before relying on the renamed volume."
    fi
done
ports="${PREFLIGHT_PORTS:-${POSTGRES_HOST_PORT:-5432},${VALKEY_HOST_PORT:-6379},8000,5173}"
for profile in ${profiles//,/ }; do
    case "$profile" in
        streams) ports="$ports,19092" ;;
        lake) ports="$ports,8333" ;;
        models) ports="$ports,11434" ;;
        observability) ports="$ports,9090,3000" ;;
    esac
done
for port in ${ports//,/ }; do
    [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -gt 0 ] && [ "$port" -le 65535 ] || { echo "Invalid preflight port" >&2; exit 1; }
    if python3 - "$port" <<'PY'
import socket
import sys
with socket.socket() as sock:
    try:
        sock.bind(('0.0.0.0', int(sys.argv[1])))
    except OSError:
        sys.exit(1)
PY
    then
        echo "Port $port is free"
    else
        owned=""
        candidates=$("$engine" ps --filter "label=com.docker.compose.project=$project" --format '{{.ID}}')
        while IFS= read -r candidate; do
            [ -n "$candidate" ] || continue
            mappings=$("$engine" port "$candidate")
            if printf '%s\n' "$mappings" | awk -v port="$port" '$NF ~ ":" port "$" {found=1} END {exit !found}'; then
                owned="$candidate"
                break
            fi
        done <<< "$candidates"
        [ -n "$owned" ] || { echo "Port $port is occupied outside Compose project $project" >&2; exit 1; }
        echo "Port $port belongs to Compose project $project"
    fi
done
