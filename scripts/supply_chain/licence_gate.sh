#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "${1:-}" == --fixture && $# == 2 ]]; then
  poetry run python scripts/supply_chain/licence_metadata.py --fixture "$2"
  exit
fi
if [[ $# != 0 ]]; then echo "Usage: $0 [--fixture DIR]" >&2; exit 2; fi
work=$(mktemp -d)
read -r -a packages <<< "$(poetry run python scripts/supply_chain/licence_metadata.py --names)"
poetry run pip-licenses --format=json --packages "${packages[@]}" > "$work/python.json"
# The canonical SPDX check also rejects missing packages and invalid exceptions.
allowed=$(poetry run python scripts/supply_chain/licence_metadata.py --metadata "$work/python.json")
read -r -a ignored <<< "$(poetry run python scripts/supply_chain/licence_metadata.py --ignored)"
args=()
if [[ ${#ignored[@]} -gt 0 ]]; then args=(--ignore-packages "${ignored[@]}"); fi
poetry run pip-licenses --packages "${packages[@]}" --allow-only "$allowed" "${args[@]}"
osi=$(sed '/^#/d; /^[[:space:]]*$/d' scripts/supply_chain/osi-licences.txt | paste -sd ';')
# The repository's private first-party root is outside the third-party licence policy.
poetry run python scripts/supply_chain/collect_npm.py > "$work/npm.json"
poetry run python scripts/supply_chain/licence_metadata.py --npm-metadata "$work/npm.json"
npm_ignored=$(poetry run python scripts/supply_chain/licence_metadata.py --npm-ignored "$work/npm.json")
(cd ui && npm exec --yes --package=license-checker-rseidelsohn@5.0.1 -- license-checker-rseidelsohn --production --excludePackages "ai-platform-ui@2.0.0${npm_ignored:+;$npm_ignored}" --onlyAllow "$osi")
echo "licence gate ok: Python and npm"
