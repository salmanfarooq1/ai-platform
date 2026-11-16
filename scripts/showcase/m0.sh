#!/usr/bin/env bash
set -euo pipefail
set +x
cd "$(dirname "$0")/../.."
if [[ -n "${SHOWCASE_PYTHON:-}" ]]; then
  exec "$SHOWCASE_PYTHON" -m scripts.showcase.m0 "$@"
fi
if command -v poetry >/dev/null 2>&1; then
  exec poetry run python -m scripts.showcase.m0 "$@"
fi
printf '%s\n' 'FAIL m0: install poetry on PATH or set SHOWCASE_PYTHON to the project Python executable' >&2
exit 1
