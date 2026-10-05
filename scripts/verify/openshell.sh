#!/usr/bin/env bash
# Run Sprint 009 acceptance A2 to A5 against a real OpenShell gateway and print PASS, FAIL or SKIP per check.
#
#     OPENSHELL_SANDBOX_IMAGE=<image with python3, user "sandbox", /sandbox/work> scripts/verify/openshell.sh
#
# Needs a Linux or WSL 2 host with Docker (or Podman), a running OpenShell gateway registered for the current user, Postgres
# and Redis (`docker compose up -d postgres redis`). docs/operations.md covers the install and the kernel requirements.
# Optional: OPENSHELL_ENDPOINT (gateway host:port), VERIFY_GATEWAY_HOST (an address of this machine the sandbox can reach, not
# loopback; default: the Docker bridge address), VERIFY_PORT (default 8010).
#
# Exit status: 0 when every check passed, 1 when one failed, 2 when the host cannot run it.
set -uo pipefail
cd "$(dirname "$0")/../.."

if [ "$(uname -s)" != "Linux" ]; then
    echo "SKIP  OpenShell sandboxes need a Linux kernel (Landlock and seccomp). Use Linux or WSL 2."
    exit 2
fi
command -v docker >/dev/null || { echo "SKIP  docker is needed for the Docker driver of the OpenShell gateway"; exit 2; }
command -v poetry >/dev/null || { echo "SKIP  poetry is needed (poetry install --with dev)"; exit 2; }

if ! poetry run python -c "import openshell" >/dev/null 2>&1; then
    echo "installing the pinned SDK wheel (openshell==0.1.2, by hash) into the project environment..."
    poetry run pip install --quiet --no-deps --require-hashes -r scripts/verify/openshell-requirements.txt || {
        echo "FAIL  the pinned wheel could not be installed"; exit 1; }
fi

echo "--- the SDK surface the driver uses"
poetry run python scripts/verify/openshell_sdk_surface.py || exit 1
echo "--- A2 to A5 against the gateway"
exec poetry run python scripts/verify/openshell_live.py
