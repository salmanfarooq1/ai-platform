#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export GRYPE_CHECK_FOR_APP_UPDATE=false
work=$(mktemp -d)
mkdir -p sbom/checks/images
: > sbom/checks/images/identities.tsv
status=0
declare -A scan_results
scan() {
  echo "Scanning $1"
  if ! identity=$(docker image inspect --format '{{.Id}}' "${1#docker:}"); then
    echo "Cannot inspect final image identity: $1" >&2
    status=1
    return
  fi
  if [[ ! "$identity" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Invalid final image identity: $1" >&2
    status=1
    return
  fi
  printf '%s\t%s\n' "$1" "$identity" >> sbom/checks/images/identities.tsv
  if [[ ${scan_results[$identity]+seen} ]]; then
    echo "Reusing immutable image result: $1 -> $identity (exit ${scan_results[$identity]})"
    return
  fi
  report="sbom/checks/images/${identity#sha256:}.cdx.json"
  config="$work/grype-${identity#sha256:}.yaml"
  if ! poetry run python scripts/supply_chain/image_exceptions.py \
      --image-ref "${1#docker:}" --output "$config"; then
    status=1
    return
  fi
  # Preserve failures while completing the other independent image checks.
  if timeout 900 grype "docker:$identity" --config "$config" --only-fixed --fail-on critical --output cyclonedx-json --file "$report"; then
    scan_results[$identity]=0
    echo "Image gate passed: $1"
  else
    code=$?
    scan_results[$identity]=$code
    echo "Image gate failed: $1 (exit $code)" >&2
    status=1
  fi
}
if docker build -t gap-supply-chain:scan .; then
  scan docker:gap-supply-chain:scan
else
  echo 'Application build failed; continuing independent image checks.' >&2
  status=1
fi
if docker build -f ui/Dockerfile.ui -t gap-supply-chain:ui ui/; then
  scan docker:gap-supply-chain:ui
else
  echo 'UI image build failed; continuing independent image checks.' >&2
  status=1
fi
# Include optional profiles and deduplicate shared init/service images. Build-only images are scanned above.
# Share the YAML-aware pin collector, including flow mappings and merged anchors.
# It emits image references only, never rendered environments or credentials.
poetry run python scripts/supply_chain/check_pins.py --compose-images > "$work/images.txt"
poetry run python scripts/supply_chain/check_pins.py --built-services > "$work/builds.txt"
while IFS= read -r service; do
  [[ -n "$service" ]] || continue
  if docker compose --project-name gap-supply-chain --profile '*' build "$service"; then
    scan "docker:gap-supply-chain-$service"
  else
    echo "Service image build failed: $service" >&2
    status=1
  fi
done < "$work/builds.txt"
while IFS= read -r image; do
  [[ "$image" == *@sha256:* ]] || { echo "Unpinned registry image: $image" >&2; status=1; continue; }
  # Pull through the daemon to reuse its layers and preserve the digest check.
  # This also avoids repeated direct registry fetches during cataloguing.
  if timeout 900 docker pull "$image"; then
    scan "docker:$image"
  else
    echo "Image pull failed: $image" >&2
    status=1
  fi
done < "$work/images.txt"
echo "Image scan completed: status=$status"
exit "$status"
