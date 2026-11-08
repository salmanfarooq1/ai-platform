#!/usr/bin/env bash
# Prerequisites (Poetry groups, npm ci, Docker) are installed by the workflow.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p sbom/checks
status=0
check() {
  local name="$1"
  shift
  local code=0
  if "$@" > "sbom/checks/$name.log" 2>&1; then
    code=0
  else
    code=$?
    status=1
  fi
  cat "sbom/checks/$name.log"
  printf '%s\t%s\n' "$name" "$code" >> sbom/checks/results.tsv
}
: > sbom/checks/results.tsv
check exports scripts/supply_chain/export_locks.sh --check
check pins poetry run python scripts/supply_chain/check_pins.py
check licence scripts/supply_chain/licence_gate.sh
check sbom scripts/supply_chain/sbom.sh
check scanners scripts/supply_chain/install_scanners.sh "$PWD/sbom/scanners"
export PATH="$PWD/sbom/scanners:$PATH"
if [[ "${SKIP_IMAGE_SCAN:-false}" == "true" ]]; then
  printf 'Image scan skipped: no source or dependency paths changed.\n' | tee sbom/checks/images.log
  printf 'images\tskipped\n' >> sbom/checks/results.tsv
else
  check images scripts/supply_chain/image_scan.sh
fi
cat sbom/checks/results.tsv
exit "$status"
