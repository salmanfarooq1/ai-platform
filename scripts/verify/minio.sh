#!/usr/bin/env bash
# Run the object store contract suite against a live MinIO (Sprint 006, acceptance A2/A4 "live MinIO run").
#
#     scripts/verify/minio.sh            # starts a MinIO container, runs the suite, removes the container
#     MINIO_ENDPOINT=http://host:9000 MINIO_ACCESS_KEY=... MINIO_SECRET_KEY=... MINIO_BUCKET=... scripts/verify/minio.sh
#                                         # uses a MinIO (or any S3 API) you already run; nothing is started
#
# Not verified in the Sprint 006 build environment: the minio/minio image could not be pulled there
# (docker.io/minio/minio: pull access denied; quay.io: forbidden). The S3 adapter was run against the same contract
# suite with an in-memory S3 client instead (tests/contracts/test_object_store_contract.py, `s3-fake-client`).
set -euo pipefail
cd "$(dirname "$0")/../.."

started=""
cleanup() { [ -n "$started" ] && docker rm -f "$started" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [ -z "${MINIO_ENDPOINT:-}" ]; then
    command -v docker >/dev/null || { echo "docker is needed to start MinIO (or set MINIO_ENDPOINT)"; exit 2; }
    export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-gapminio}"
    export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-gapminio-secret}"
    export MINIO_BUCKET="${MINIO_BUCKET:-gap-contract}"
    port="${MINIO_PORT:-9100}"
    started="gap-minio-verify"
    docker rm -f "$started" >/dev/null 2>&1 || true
    docker run -d --name "$started" -p "127.0.0.1:${port}:9000" \
        -e MINIO_ROOT_USER="$MINIO_ACCESS_KEY" -e MINIO_ROOT_PASSWORD="$MINIO_SECRET_KEY" \
        minio/minio:latest server /data >/dev/null
    export MINIO_ENDPOINT="http://127.0.0.1:${port}"
    for _ in $(seq 1 60); do
        curl -fs "${MINIO_ENDPOINT}/minio/health/live" >/dev/null && break
        sleep 1
    done
    # Create the bucket through the S3 API with the SDK the adapter uses.
    poetry run python - <<'PY'
import os

import boto3

client = boto3.client(
    "s3", endpoint_url=os.environ["MINIO_ENDPOINT"], aws_access_key_id=os.environ["MINIO_ACCESS_KEY"],
    aws_secret_access_key=os.environ["MINIO_SECRET_KEY"], region_name="us-east-1",
)
client.create_bucket(Bucket=os.environ["MINIO_BUCKET"])
print("bucket", os.environ["MINIO_BUCKET"], "ready")
PY
fi

poetry run pytest tests/contracts/test_object_store_contract.py -q -p no:cacheprovider -rs
