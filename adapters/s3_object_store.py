"""Object store on an S3 API (Cloudflare R2, MinIO, S3). Content-addressed: the object key is the SHA-256.

boto3 is synchronous, so each call runs in a worker thread. The client can be injected for tests.
"""
import asyncio
import hashlib
import re
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ports.objects import ObjectNotFound

_KEY = re.compile(r"^[0-9a-f]{64}$")
_MISSING = {"404", "NoSuchKey", "NotFound"}


class S3ObjectStore:
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    @classmethod
    def from_settings(
        cls, *, endpoint_url: str, bucket: str, access_key_id: str, secret_access_key: str, region: str = "auto"
    ) -> "S3ObjectStore":
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return cls(bucket, client)

    async def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        if await self.exists(key):
            return key  # same bytes: written once
        await asyncio.to_thread(self._client.put_object, Bucket=self._bucket, Key=key, Body=data)
        return key

    async def get(self, key: str) -> bytes:
        if not _KEY.match(key):
            raise ObjectNotFound(key)
        try:
            response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
            body: bytes = await asyncio.to_thread(response["Body"].read)
            return body
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING:
                raise ObjectNotFound(key) from None
            raise

    async def exists(self, key: str) -> bool:
        if not _KEY.match(key):
            return False
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _MISSING:
                return False
            raise
        return True
