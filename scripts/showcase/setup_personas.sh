#!/usr/bin/env bash
# Run within the existing Poetry environment. Credentials are environment-only.
# Pass an existing tenant slug; valid private credentials are reused on reruns.
set +x
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
exec "${SHOWCASE_PYTHON:-python}" -m scripts.showcase.personas "$@"
