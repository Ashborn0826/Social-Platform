"""S3-compatible (boto3) implementation of ObjectStorage.

Works against real AWS S3 or any S3-compatible service (MinIO, Cloudflare R2,
Backblaze B2, etc.). Configure via `settings.s3_endpoint_url` for non-AWS.

Presigned URLs use boto3's `generate_presigned_url`, which signs the request
with the configured AWS credentials. Clients PUT/GET against the signed URL
directly without going through our API server.
"""
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


class S3Backend:
    def __init__(
        self,
        bucket: str,
        region: str,
        endpoint_url: Optional[str] = None,
    ):
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4"),
        )

    def presigned_put_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_seconds,
        )

    def presigned_get_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def size(self, key: str) -> int:
        try:
            r = self.client.head_object(Bucket=self.bucket, Key=key)
            return int(r["ContentLength"])
        except ClientError:
            return 0

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    def get_bytes(self, key: str) -> bytes:
        r = self.client.get_object(Bucket=self.bucket, Key=key)
        return r["Body"].read()