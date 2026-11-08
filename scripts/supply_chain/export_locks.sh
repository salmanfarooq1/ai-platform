#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mode="${1:-}"
if [[ -n "$mode" && "$mode" != --check ]]; then echo "Usage: $0 [--check]" >&2; exit 2; fi
work=$(mktemp -d)
# poetry-plugin-export 1.10.1 includes hashes by default; --with-hashes does not exist.
poetry export --only main --format requirements.txt --output "$work/main.txt"
poetry export --with dev --format requirements.txt --output "$work/dev.txt"
python scripts/supply_chain/check_exports.py "$work/main.txt" "$work/dev.txt"
if [[ "$mode" == --check ]]; then
  diff -u requirements/main.txt "$work/main.txt"
  diff -u requirements/dev.txt "$work/dev.txt"
else
  mkdir -p requirements
  cp "$work/main.txt" requirements/main.txt
  cp "$work/dev.txt" requirements/dev.txt
fi
echo "hash exports match poetry.lock"
