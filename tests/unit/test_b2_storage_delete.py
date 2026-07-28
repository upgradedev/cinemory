"""Unit tests for B2Storage.delete — added additively for multitenancy's
DELETE /me/data. Drives the adapter through a small in-memory S3-compatible
stub (no boto3/creds needed in CI), mirroring
``tests/unit/test_b2_storage_index.py``'s pattern — extended with
``delete_object`` (that file's original stub predates DELETE support).
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
    """Minimal in-memory S3 stub (put/get/delete) shared across instances."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.store[(Bucket, Key)] = Body
        return {}

    def get_object(self, *, Bucket, Key):  # noqa: N803
        if (Bucket, Key) not in self.store:
            raise KeyError(Key)
        return {"Body": _Body(self.store[(Bucket, Key)])}

    def delete_object(self, *, Bucket, Key):  # noqa: N803
        # Real S3/B2 DeleteObject does not error on a missing key — mirrored
        # here (pop with a default) so the stub matches production semantics.
        self.store.pop((Bucket, Key), None)
        return {}


@pytest.fixture(autouse=True)
def _b2_env(monkeypatch):
    for name in _B2_ENV:
        monkeypatch.delenv(name, raising=False)
    # A non-empty prefix is deliberate — see test_b2_storage_index.py's own
    # fixture for why (makes a logical-vs-actual key mixup observable).
    monkeypatch.setenv("B2_BUCKET_NAME", "cinemory-live")
    monkeypatch.setenv("B2_S3_ENDPOINT", "https://s3.eu-central-003.backblazeb2.com")
    monkeypatch.setenv("B2_KEY_PREFIX", "cin")


def _durable_index_keys(s3: _FakeS3) -> set[str]:
    raw = s3.store[("cinemory-live", "cin/index.jsonl")]
    return {json.loads(line)["key"] for line in raw.decode("utf-8").splitlines() if line}


def test_delete_removes_the_prefixed_object_and_the_logical_index_row():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    key = "graduation/reels/aa/bb/reel.mp4"
    store.put(key, b"video-bytes", content_type="video/mp4")
    assert ("cinemory-live", f"cin/{key}") in s3.store

    store.delete(key)

    assert ("cinemory-live", f"cin/{key}") not in s3.store
    assert store.index == []
    assert _durable_index_keys(s3) == set()


def test_delete_only_removes_the_matching_key_from_the_durable_index():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    store.put("r/photos/aa/a1/one.png", b"1", content_type="image/png")
    store.put("r/reels/bb/b1/reel.mp4", b"22", content_type="video/mp4")

    store.delete("r/photos/aa/a1/one.png")

    assert [r["key"] for r in store.index] == ["r/reels/bb/b1/reel.mp4"]
    assert _durable_index_keys(s3) == {"r/reels/bb/b1/reel.mp4"}


def test_delete_does_not_resurrect_the_row_via_persist_indexs_remote_reread():
    """Regression test for the resurrection bug in the FIRST cut of this
    method: ``_persist_index``'s merge-on-write re-reads the bucket's
    ``index.jsonl`` BEFORE merging — and that re-read is, by construction,
    the pre-delete snapshot (nothing has rewritten it yet). A plain
    ``dict.update()`` union can only ADD/overwrite keys, never remove one
    absent from the update source — so without explicitly telling
    ``_persist_index`` which key to drop from that stale remote snapshot
    (the ``removed=`` parameter), the very act of persisting a delete would
    silently write the deleted row right back into the durable index."""
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    key = "r/reels/dd/d1/reel.mp4"
    store.put(key, b"x", content_type="video/mp4")
    assert _durable_index_keys(s3) == {key}

    store.delete(key)

    assert _durable_index_keys(s3) == set(), "delete resurrected its own row"
    assert store.index == []

    # A fresh instance (e.g. a new Cloud Run worker) must also see the
    # deletion, not a resurrected row — the bucket, not any one Python
    # object, is the source of truth.
    reader = B2Storage(client=s3)
    assert reader.index == []


def test_delete_of_a_missing_key_is_a_no_op_not_an_error():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    store.delete("never-existed")  # must not raise
    assert store.index == []


def test_delete_is_idempotent():
    s3 = _FakeS3()
    store = B2Storage(client=s3)
    store.put("k", b"v")
    store.delete("k")
    store.delete("k")  # second call: still a clean no-op
    assert store.index == []
