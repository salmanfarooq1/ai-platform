"""Verify boto3 SigV4 GET and PUT against an explicitly configured live S3 endpoint."""
import hashlib
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import boto3
from botocore.config import Config


def expect_denied(url: str, reason: str) -> None:
    """Keep signed URLs and response bodies out of captured verification logs."""
    try:
        with urlopen(url, timeout=20):
            raise AssertionError(f"Presigned {reason} request was accepted")
    except HTTPError as exc:
        assert exc.code == 403, f"Presigned {reason} returned HTTP {exc.code}, expected 403"


def main() -> None:
    client = boto3.client(
        "s3", endpoint_url=os.environ["S3_LIVE_ENDPOINT"],
        aws_access_key_id=os.environ["S3_LIVE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_LIVE_SECRET_KEY"],
        region_name="us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    bucket = os.environ["S3_LIVE_BUCKET"]
    data = b"signed object contract\x00\xff"
    key = f"presign-contract/{uuid4().hex}"
    put_url = client.generate_presigned_url("put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=60)
    with urlopen(Request(put_url, data=data, method="PUT"), timeout=20) as response:
        assert response.status == 200
    get_url = client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=60)
    with urlopen(get_url, timeout=20) as response:
        assert response.status == 200 and response.read() == data
    parts = urlsplit(get_url)
    expect_denied(urlunsplit(parts._replace(path=parts.path + "-other")), "changed-key")
    expired_url = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=1,
    )
    time.sleep(2.1)
    expect_denied(expired_url, "expired")
    print("Presigned SigV4 PUT and GET passed; SHA-256", hashlib.sha256(data).hexdigest())
    print("Presigned changed-key and expired GET requests both denied with HTTP 403")


if __name__ == "__main__":
    main()
