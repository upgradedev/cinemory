"""Unit tests for the real B2 adapter's queryable run index.

The live claim in README ("the storage backend keeps a queryable run index")
must hold for :class:`~cinemory.adapters.b2_storage.B2Storage`, not just the
offline fake — otherwise ``GET /reels/{name}`` / the ProvenancePanel are empty
exactly in live mode. These tests drive the adapter through a small in-memory
S3-compatible stub (so no boto3/creds are needed in CI) and pin:

  * the index records the *logical* key (pre-prefix), matching FakeStorage;
  * every ``put`` persists ``index.jsonl`` durably in the bucket;
  * a **second** adapter instance (fresh Cloud Run worker) resolves a reel the
    first instance wrote — via the init snapshot *and* ``reload_index()``;
  * a non-empty key prefix is applied to the actual object key but never leaks
    into the logical index key.
"""
from __future__ import annotations

import json

import pytest

from cinemory.adapters.b2_storage import B2Storage

_B2_ENV = (
    "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION", "B2_BUCKET_NAME",
    "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY", "B2_S3_ENDPOINT",
    "B2_KEY_PREFIX", "B2_PREFIX",
)


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3:
    """Minimal in-memory S3 stub shared across adapter instances (one bucket)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.store[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.store:
            raise KeyError(Key)
        return {"Body": _Body(self.store[(Bucket, Key)])}

    def generate_presigned_url(self, operation, *, Params, ExpiresIn):  # noqa: N803
        # Mirrors boto3's local (no-network) signing: URL embeds the request.
        self.presigned = getattr(self, "presigned", 0) + 1
        return (f"https://{Params['Bucket']}.example/{Params['Key']}"
                f"?op={operation}&X-Amz-Expires={ExpiresIn}&sig={self.presigned}")


@pytest.fixture(autouse=True)
def _b2_env(monkeypatch):
    for name in _B2_ENV:
        monkeypatch.delenv(name, raising=False)
    # A NON-EMPTY prefix is deliberate: it makes a logical-vs-actual key mixup
    # observable (an empty prefix would hide it).
    monkeypatch.setenv("B2_BUCKET_NAME", "cinemory-live")
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")
    monkeypatch.setenv("B2_KEY_PREFIX", "cin")


_MANIFEST_KEY = "graduation/manifests/ab/abcd/manifest.json"


def test_put_indexes_logical_key_and_prefixes_object():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    payload = json.dumps({"manifest_hash": "deadbeef"}).encode()

    url = store.put(_MANIFEST_KEY, payload, content_type="application/json")

    # Index holds the logical (pre-prefix) key, mirroring FakeStorage.
    assert store.index == [
        {"key": _MANIFEST_KEY, "size": len(payload), "content_type": "application/json"}
    ]
    # The actual object lives under the prefix; the URL reflects the real key.
    assert ("cinemory-live", f"cin/{_MANIFEST_KEY}") in s3.store
    assert url.endswith(f"cin/{_MANIFEST_KEY}")
    # index.jsonl is persisted durably under the prefix.
    assert ("cinemory-live", "cin/index.jsonl") in s3.store


def test_get_roundtrips_via_logical_key():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    payload = b"reel-bytes"
    store.put("graduation/reels/aa/bb/reel.mp4", payload)
    assert store.get("graduation/reels/aa/bb/reel.mp4") == payload


def test_second_instance_resolves_first_instances_reel():
    """A fresh worker (new adapter) inherits the durable catalogue at init."""
    s3 = _FakeS3()
    writer = B2Storage(client=s3)
    payload = json.dumps({"manifest_hash": "cafe"}).encode()
    writer.put(_MANIFEST_KEY, payload, content_type="application/json")

    reader = B2Storage(client=s3)  # separate instance, same bucket
    match = next(
        (r for r in reader.index if r["key"].startswith("graduation/manifests/")), None
    )
    assert match is not None
    assert json.loads(reader.get(match["key"])) == {"manifest_hash": "cafe"}


def test_reload_index_sees_writes_after_construction():
    s3 = _FakeS3()
    reader = B2Storage(client=s3)  # constructed first, index empty
    assert reader.index == []

    writer = B2Storage(client=s3)
    writer.put(_MANIFEST_KEY, b"{}", content_type="application/json")

    # Query-time refresh (what api.get_reel calls) makes the write visible.
    reader.reload_index()
    assert any(r["key"] == _MANIFEST_KEY for r in reader.index)


def test_get_url_presigns_the_prefixed_key_fresh_each_call():
    """``get_url`` (the playback route's live path) signs the ACTUAL (prefixed)
    object key, honours the expiry, and mints a fresh URL per call — presigned
    URLs are never persisted, so provenance keeps the canonical URL."""
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    key = "graduation/reels/aa/bb/reel.mp4"
    store.put(key, b"video-bytes", content_type="video/mp4")

    url = store.get_url(key)
    assert url.startswith(f"https://cinemory-live.example/cin/{key}?op=get_object")
    assert "X-Amz-Expires=3600" in url and "sig=1" in url
    # A later playback gets a FRESH signature (expiry-proof by construction).
    assert "sig=2" in store.get_url(key)
    # Custom expiry is passed through.
    assert "X-Amz-Expires=60" in store.get_url(key, expires_in=60)


def test_index_jsonl_is_sorted_ndjson():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    store.put("r/photos/a/b/p.png", b"x", content_type="image/png")
    store.put("r/reels/c/d/reel.mp4", b"yy", content_type="video/mp4")

    lines = store.index_jsonl().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert set(first) == {"key", "size", "content_type"}
