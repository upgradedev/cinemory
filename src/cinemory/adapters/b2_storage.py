"""Real Backblaze B2 storage adapter (S3-compatible, via boto3).

B2 exposes an S3-compatible API, so any S3 client works. Credentials come from
the environment; nothing is hard-coded. ``boto3`` is imported lazily so the
package (and offline CI) does not require it.

Env (each accepts the legacy name below, or Backblaze's own canonical name so a
user who already exports the canonical set needs no ``.env`` edit — resolution
lives in :func:`cinemory.config.resolve_b2_config`):
  B2_BUCKET_NAME        target bucket
  B2_ENDPOINT_URL       e.g. https://s3.eu-central-003.backblazeb2.com
                        (canonical: B2_S3_ENDPOINT; a missing scheme is added)
  B2_KEY_ID             application key id   (canonical: B2_APPLICATION_KEY_ID)
  B2_APP_KEY            application key       (canonical: B2_APPLICATION_KEY)
"""
from __future__ import annotations


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

        # Lazy import avoids any import-time coupling with config (which imports
        # the adapters package). Resolution accepts legacy + canonical env names.
        from ..config import resolve_b2_config

        cfg = resolve_b2_config()
        self.bucket = bucket or cfg.bucket
        self.endpoint_url = endpoint_url or cfg.endpoint_url
        access_key_id = key_id or cfg.key_id
        secret_access_key = app_key or cfg.app_key
        if not self.bucket:
            raise RuntimeError("B2 bucket not configured (set B2_BUCKET_NAME)")
        if not self.endpoint_url:
            raise RuntimeError(
                "B2 endpoint not configured (set B2_ENDPOINT_URL or B2_S3_ENDPOINT)"
            )
        if not access_key_id or not secret_access_key:
            raise RuntimeError(
                "B2 credentials not configured (set B2_KEY_ID/B2_APP_KEY or "
                "B2_APPLICATION_KEY_ID/B2_APPLICATION_KEY)"
            )
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
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
