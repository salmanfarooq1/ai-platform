#!/usr/bin/env bash
# Live SeaweedFS S3 contracts and SigV4 signed GET/PUT. No store or volume is removed.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ -z "${S3_LIVE_ENDPOINT:-}" ]; then
    command -v docker >/dev/null || { echo "docker is needed (or set S3_LIVE_ENDPOINT)"; exit 2; }
    export S3_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-gap_local_only_access}"
    export S3_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-gap_local_only_secret}"
    export S3_BUCKET="${S3_BUCKET:-gap-local}"
    docker compose --profile lake build seaweedfs seaweedfs-init
    docker compose --profile lake up -d --wait seaweedfs
    docker compose --profile lake run --rm seaweedfs-init
    export S3_LIVE_ENDPOINT="http://127.0.0.1:8333"
    export S3_LIVE_ACCESS_KEY="$S3_ACCESS_KEY_ID" S3_LIVE_SECRET_KEY="$S3_SECRET_ACCESS_KEY" S3_LIVE_BUCKET="$S3_BUCKET"
fi
for name in S3_LIVE_ACCESS_KEY S3_LIVE_SECRET_KEY S3_LIVE_BUCKET; do
    [ -n "${!name:-}" ] || { echo "Required variable: $name" >&2; exit 2; }
done
poetry run pytest tests/contracts/test_object_store_contract.py -k seaweedfs -q -p no:cacheprovider -rs
poetry run python scripts/verify/seaweedfs_presign.py
