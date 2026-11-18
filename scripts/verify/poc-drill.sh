#!/usr/bin/env bash
# The M0 recovery drill: up, seed, deny with a saved receipt, backup, checked down, restore up, compare counts and heads,
# verify the saved receipt offline, make a new governed call, then fully tear the fixture stack down (Sprint 015 WP4).
#
#   scripts/verify/poc-drill.sh <stack>
#
# Public seams only: the `poc` commands, the public HTTP API and the offline receipt verifier (see poc_drill.py).
# Every step prints one `PASS <step>` or `FAIL <step>` line. It never prints SKIP: a missing prerequisite or any
# failed step exits nonzero. The stack must not exist yet; the drill owns it and destroys it when it ends.
set -euo pipefail
set +x
cd "$(dirname "$0")/../.."
if [[ $# -ne 1 || -z "${1:-}" ]]; then
  printf '%s\n' 'FAIL prerequisites: usage: scripts/verify/poc-drill.sh <stack>'
  exit 2
fi
if [[ -n "${SHOWCASE_PYTHON:-}" ]]; then
  exec "$SHOWCASE_PYTHON" scripts/verify/poc_drill.py "$1"
fi
if command -v poetry >/dev/null 2>&1; then
  exec poetry run python scripts/verify/poc_drill.py "$1"
fi
printf '%s\n' 'FAIL prerequisites: install poetry on PATH or set SHOWCASE_PYTHON to the project Python executable'
exit 1
