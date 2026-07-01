"""Real Backblaze B2 storage adapter (S3-compatible, via boto3).

B2 exposes an S3-compatible API, so any S3 client works. Credentials come from
the environment; nothing is hard-coded. ``boto3`` is imported lazily so the
package (and offline CI) does not require it.

Env:
  B2_BUCKET_NAME        target bucket
  B2_ENDPOINT_URL       e.g. https://s3.eu-central-003.backblazeb2.com
  B2_KEY_ID             application key id  (AWS_ACCESS_KEY_ID equivalent)
  B2_APP_KEY            application key      (AWS_SECRET_ACCESS_KEY equivalent)
"""
from __future__ import annotations

import os


class B2Storage:
    def __init__(
        self,
        bucket: str | None = None,
        *,
        endpoint_url: str | None = None,
        key_id: str | None = None,
        app_key: str | None = None,
    ) -> None:
        try:
            import boto3  # noqa: F401
        except ImportError as exc:  # pragma: no cover - real-path only
            raise RuntimeError("boto3 is required for B2Storage: pip install boto3") from exc
        import boto3

        self.bucket = bucket or os.environ["B2_BUCKET_NAME"]
        self.endpoint_url = endpoint_url or os.environ["B2_ENDPOINT_URL"]
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=key_id or os.environ["B2_KEY_ID"],
            aws_secret_access_key=app_key or os.environ["B2_APP_KEY"],
        )

    def put(  # pragma: no cover - real-path only
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        host = self.endpoint_url.replace("https://", "").rstrip("/")
        return f"https://{self.bucket}.{host}/{key}"

    def get(self, key: str) -> bytes:  # pragma: no cover - real-path only
        return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:  # pragma: no cover - real-path only
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
