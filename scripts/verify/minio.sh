#!/usr/bin/env bash
# Compatibility entry point for historical documentation. The supported live store is SeaweedFS.
set -euo pipefail
exec "$(dirname "$0")/seaweedfs.sh" "$@"
