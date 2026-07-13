"""Real Backblaze B2 storage adapter (S3-compatible, via boto3).

B2 exposes an S3-compatible API, so any S3 client works. Credentials come from
the environment; nothing is hard-coded. ``boto3`` is imported lazily so the
package (and offline CI) does not require it.

Like :class:`~cinemory.adapters.fake_storage.FakeStorage`, this adapter keeps a
**queryable run index**: every ``put`` appends a row (key + size + content-type)
to an ``index.jsonl`` object persisted *in the bucket itself*. That makes the
catalogue durable and multi-instance safe — a scale-to-zero Cloud Run instance
that never saw a write can still answer ``GET /reels/{name}`` by re-reading the
index from B2 (see :meth:`reload_index`). The index mirrors ``FakeStorage.index``
exactly, so the offline and live paths expose the identical provenance surface.

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

import json

# Object holding the run index (JSONL catalogue), relative to the key prefix.
_INDEX_NAME = "index.jsonl"


class B2Storage:
    def __init__(
        self,
        bucket: str | None = None,
        *,
        endpoint_url: str | None = None,
        key_id: str | None = None,
        app_key: str | None = None,
        client: object | None = None,
    ) -> None:
        # Lazy import avoids any import-time coupling with config (which imports
        # the adapters package). Resolution accepts legacy + canonical env names.
        from ..config import resolve_b2_config

        cfg = resolve_b2_config()
        self.bucket = bucket or cfg.bucket
        self.endpoint_url = endpoint_url or cfg.endpoint_url
        access_key_id = key_id or cfg.key_id
        secret_access_key = app_key or cfg.app_key

        # Resolve key prefix from config; ensure it ends with a slash if non-empty
        prefix = cfg.key_prefix or ""
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        self.key_prefix = prefix
        self._index_key = f"{self.key_prefix}{_INDEX_NAME}"

        if not self.bucket:
            raise RuntimeError("B2 bucket not configured (set B2_BUCKET_NAME)")
        if not self.endpoint_url:
            raise RuntimeError(
                "B2 endpoint not configured (set B2_ENDPOINT_URL or B2_S3_ENDPOINT)"
            )

        # ``client`` is a test seam (inject an S3-compatible stub); the real path
        # builds a boto3 client, which is the only branch that needs boto3 + creds.
        if client is not None:
            self._client = client
        else:  # pragma: no cover - real-path only (needs boto3 + live creds)
            if not access_key_id or not secret_access_key:
                raise RuntimeError(
                    "B2 credentials not configured (set B2_KEY_ID/B2_APP_KEY or "
                    "B2_APPLICATION_KEY_ID/B2_APPLICATION_KEY)"
                )
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "boto3 is required for B2Storage: pip install boto3"
                ) from exc
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
            )

        # Seed the in-memory index from whatever is already durable in the bucket
        # so a fresh instance inherits the full catalogue.
        self.index: list[dict] = self.reload_index()

    # ── run index (queryable catalogue, mirrors FakeStorage.index) ────────────
    def index_jsonl(self) -> str:
        """Serialise the asset catalogue (Genblaze ParquetSink analogue)."""
        return "\n".join(json.dumps(row, sort_keys=True) for row in self.index)

    def reload_index(self) -> list[dict]:
        """Re-read ``index.jsonl`` from the bucket (query-time freshness).

        Best-effort: a missing index (first run) or any read error yields an
        empty catalogue rather than raising, so lookups degrade to "not found"
        instead of 500-ing.
        """
        try:
            raw = self._client.get_object(Bucket=self.bucket, Key=self._index_key)[
                "Body"
            ].read()
        except Exception:  # missing/unreadable index (first run) → empty catalogue
            self.index = []
            return self.index
        rows: list[dict] = []
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        self.index = rows
        return self.index

    def _persist_index(self) -> None:
        self._client.put_object(
            Bucket=self.bucket,
            Key=self._index_key,
            Body=self.index_jsonl().encode("utf-8"),
            ContentType="application/x-ndjson",
        )

    # ── object I/O ────────────────────────────────────────────────────────────
    def put(
        self, key: str, data: bytes, *, content_type: str = "application/octet-stream"
    ) -> str:
        actual_key = f"{self.key_prefix}{key}"
        self._client.put_object(
            Bucket=self.bucket, Key=actual_key, Body=data, ContentType=content_type
        )
        # Record the *logical* key (pre-prefix), matching FakeStorage, so the API
        # can look a reel up by name and fetch it back via ``get(key)``.
        self.index.append({"key": key, "size": len(data), "content_type": content_type})
        self._persist_index()
        host = self.endpoint_url.replace("https://", "").rstrip("/")
        return f"https://{self.bucket}.{host}/{actual_key}"

    def get(self, key: str) -> bytes:
        actual_key = f"{self.key_prefix}{key}"
        return self._client.get_object(Bucket=self.bucket, Key=actual_key)["Body"].read()

    def exists(self, key: str) -> bool:  # pragma: no cover - real-path only (botocore)
        from botocore.exceptions import ClientError

        actual_key = f"{self.key_prefix}{key}"
        try:
            self._client.head_object(Bucket=self.bucket, Key=actual_key)
            return True
        except ClientError:
            return False
