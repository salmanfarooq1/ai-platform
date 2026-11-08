#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
  echo "usage: $0 [Gateway|Assurance|Agents|Data|Full]" >&2
  exit 2
fi

if (( $# == 1 )); then
  editions=("$1")
else
  editions=(Gateway Assurance Agents Data Full)
fi

for edition in "${editions[@]}"; do
  modules="$(poetry run python -c 'import sys; from core.modules import EDITIONS; name=sys.argv[1]; print(",".join(sorted(EDITIONS[name]))) if name in EDITIONS else sys.exit(2)' "$edition")" || {
    echo "unknown edition: $edition" >&2
    exit 2
  }
  echo "Smoke edition: $edition ($modules)"
  ENABLED_MODULES="$modules" poetry run pytest -m edition_smoke -q -p no:cacheprovider tests/editions
done
