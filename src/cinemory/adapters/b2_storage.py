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
        from ..config import _derive_region, resolve_b2_config

        cfg = resolve_b2_config()
        self.bucket = bucket or cfg.bucket
        self.endpoint_url = endpoint_url or cfg.endpoint_url
        access_key_id = key_id or cfg.key_id
        secret_access_key = app_key or cfg.app_key
        # Region matters: B2 REJECTS region-less presigned GET URLs with 401
        # (plain put/get tolerate a missing region, which is why this only broke
        # playback). B2_REGION wins; otherwise derive from the endpoint host —
        # re-derived from the *effective* endpoint so an explicit ``endpoint_url``
        # argument still yields the right signing region.
        self.region = cfg.region or _derive_region(self.endpoint_url)

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
        else:  # boto3 path (construction is stub-tested; live I/O needs creds)
            if not access_key_id or not secret_access_key:
                raise RuntimeError(
                    "B2 credentials not configured (set B2_KEY_ID/B2_APP_KEY or "
                    "B2_APPLICATION_KEY_ID/B2_APPLICATION_KEY)"
                )
            try:
                import boto3
                from botocore.config import Config as _BotoConfig
            except ImportError as exc:
                raise RuntimeError(
                    "boto3 is required for B2Storage: pip install boto3"
                ) from exc
            # SigV4 + an explicit region are REQUIRED for presigned URLs to
            # work against B2: a client built without them signs GET URLs that
            # B2 answers with 401 Unauthorized (proven live 2026-07-22 — the
            # box-minted presign 401'd while a region-scoped presign of the
            # same object returned 200). Direct put/get tolerate the omission,
            # so only playback broke.
            client_kwargs: dict = {
                "endpoint_url": self.endpoint_url,
                "aws_access_key_id": access_key_id,
                "aws_secret_access_key": secret_access_key,
                "config": _BotoConfig(signature_version="s3v4"),
            }
            if self.region:
                client_kwargs["region_name"] = self.region
            self._client = boto3.client("s3", **client_kwargs)

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
        self.index = self._read_remote_index_rows()
        return self.index

    def _read_remote_index_rows(self) -> list[dict]:
        """Current durable ``index.jsonl`` rows — best-effort by design.

        A missing index (first run), a read error, a corrupt line, or a
        non-row line yields FEWER rows rather than raising: readers degrade to
        "not found", and because :meth:`_persist_index` calls this on every
        put, the next merge-on-write rewrites a clean index (self-healing) —
        a corrupt remote line must never be able to fail ``put``.
        """
        try:
            raw = self._client.get_object(Bucket=self.bucket, Key=self._index_key)[
                "Body"
            ].read()
        except Exception:
            return []
        rows: list[dict] = []
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:  # corrupt line — drop; next persist writes clean
                continue
            if isinstance(row, dict) and "key" in row:
                rows.append(row)
        return rows

    def _persist_index(self) -> None:
        """Merge-on-write: union our rows with the current remote index.

        Concurrent writers (e.g. a local run and the live Cloud Run box) used
        to last-writer-wins clobber each other's ``index.jsonl`` rows, making
        the other writer's reels 404 until the rows were merged back by hand
        (bit us live 2026-07-22). Instead of writing our snapshot blindly, we
        re-read the remote index and union rows **by key** — idempotent, and
        newest-wins per key (our in-memory row, which includes the put that
        triggered this call, overlays the remote row for the same key; keys are
        content-addressed, so same-key rows are identical in practice). A small
        read-modify-write race window remains between the re-read and the put;
        that is accepted — losing it costs one index row until the next
        merge-on-write or manual reconcile, and building distributed locking
        over B2 is out of scope by design.
        """
        merged: dict[str, dict] = {row["key"]: row for row in self._read_remote_index_rows()}
        merged.update((row["key"], row) for row in self.index)
        self.index = list(merged.values())
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

    def get_url(self, key: str, *, expires_in: int = 3600) -> str:
        """Mint a FRESH time-limited presigned GET URL for ``key``.

        The bucket is private, so the durable URL returned by :meth:`put` (and
        recorded in provenance) is not directly fetchable by a browser. The API
        playback route calls this per request; the presigned URL is **never
        persisted** — manifests keep the canonical storage URL and hashes.
        Signing is local (no network round-trip).
        """
        actual_key = f"{self.key_prefix}{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": actual_key},
            ExpiresIn=expires_in,
        )

    def exists(self, key: str) -> bool:  # pragma: no cover - real-path only (botocore)
        from botocore.exceptions import ClientError

        actual_key = f"{self.key_prefix}{key}"
        try:
            self._client.head_object(Bucket=self.bucket, Key=actual_key)
            return True
        except ClientError:
            return False
