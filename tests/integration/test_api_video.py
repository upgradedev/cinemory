"""Playback route: ``GET /reels/{name}/video`` + the stable ``playback_url``.

The bucket is private, so the canonical storage URL in provenance is not
directly fetchable by a browser (it 401s). Playback therefore goes through a
stable, api-relative route that resolves the reel via the durable index and:

  * **offline / FakeStorage** — streams the stored bytes straight back
    (200, correct content-type, byte-exact vs the sealed reel hash);
  * **live / a backend exposing ``get_url``** — 302-redirects to a FRESH
    presigned GET URL minted per request (never persisted; the manifest keeps
    the canonical URL/hash).

Every reel response must carry ``playback_url`` pointing at that route so the
frontend never has to guess whether a storage URL is fetchable.
"""
from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

import cinemory.api as api

client = TestClient(api.app)


def test_api_title_is_cinemory():
    # Judge-visible at /docs — the product is Cinemory (no legacy working title).
    assert api.app.title == "Cinemory API"


def test_reel_response_carries_stable_playback_url():
    r = client.post("/reels", json={"name": "playme", "chapters": 2, "per_chapter": 1})
    assert r.status_code == 200
    assert r.json()["playback_url"] == "/reels/playme/video"


def test_upload_response_carries_playback_url_url_encoded():
    import base64

    photos = [{"filename": "p.png", "content_base64": base64.b64encode(b"px").decode()}]
    r = client.post("/reels/upload", json={"name": "my reel", "photos": photos})
    assert r.status_code == 200
    # The api-relative URL is safe to fetch verbatim (spaces etc. are encoded).
    assert r.json()["playback_url"] == "/reels/my%20reel/video"


def test_offline_video_streams_bytes_matching_the_sealed_hash():
    r = client.post("/reels", json={"name": "streamed", "chapters": 2, "per_chapter": 2})
    assert r.status_code == 200
    body = r.json()

    v = client.get(body["playback_url"])
    assert v.status_code == 200
    assert v.headers["content-type"].startswith("video/mp4")
    # The streamed bytes are the exact reel the manifest sealed.
    assert hashlib.sha256(v.content).hexdigest() == body["reel_sha256"]


def test_video_lookup_applies_the_same_name_sanitisation_as_the_manifest():
    r = client.post("/reels", json={"name": "my reel", "chapters": 1, "per_chapter": 1})
    assert r.status_code == 200
    v = client.get(r.json()["playback_url"])  # /reels/my%20reel/video
    assert v.status_code == 200
    assert len(v.content) > 0


def test_unknown_reel_video_is_404():
    assert client.get("/reels/never-generated/video").status_code == 404


def test_video_never_serves_the_provenance_embedded_variant():
    """The playback object is ``reel.mp4`` — never ``reel.provenance.mp4``
    (whose trailing embedded-manifest bytes would corrupt strict players)."""
    r = client.post("/reels", json={"name": "plainreel", "chapters": 1, "per_chapter": 1})
    body = r.json()
    v = client.get(body["playback_url"])
    assert hashlib.sha256(v.content).hexdigest() == body["reel_sha256"]
    prov = next(row for row in api._storage.index
                if row["key"].startswith("plainreel/reels/")
                and row["key"].endswith("reel.provenance.mp4"))
    assert hashlib.sha256(api._storage.get(prov["key"])).hexdigest() != body["reel_sha256"]


# ── live path: a storage backend that can mint presigned URLs → 302 ──────────
class _PresigningStorage:
    """Minimal live-shaped backend: durable index + ``get_url`` presigner."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self.index: list[dict] = []
        self.reloads = 0
        self.signed: list[str] = []

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream"):
        self._objects[key] = data
        self.index.append({"key": key, "size": len(data), "content_type": content_type})
        return f"https://bucket.example/{key}"

    def get(self, key: str) -> bytes:
        return self._objects[key]

    def exists(self, key: str) -> bool:
        return key in self._objects

    def reload_index(self) -> list[dict]:
        self.reloads += 1
        return self.index

    def get_url(self, key: str, *, expires_in: int = 3600) -> str:
        self.signed.append(key)
        return (f"https://bucket.example/{key}"
                f"?X-Amz-Expires={expires_in}&X-Amz-Signature=fresh-{len(self.signed)}")


def test_live_video_redirects_to_a_fresh_presigned_url(monkeypatch):
    storage = _PresigningStorage()
    monkeypatch.setattr(api, "_storage", storage)
    key = "livereel/reels/ab/" + "a" * 64 + "/reel.mp4"
    storage.put(key, b"real-video-bytes", content_type="video/mp4")

    live = TestClient(api.app)
    r = live.get("/reels/livereel/video", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith(f"https://bucket.example/{key}?")
    assert "X-Amz-Signature=fresh-1" in location
    # Fresh per request — a later playback never reuses a stale signed URL.
    r2 = live.get("/reels/livereel/video", follow_redirects=False)
    assert "X-Amz-Signature=fresh-2" in r2.headers["location"]
    assert storage.signed == [key, key]
    # The durable index was re-read (scale-to-zero worker resolves prior writes).
    assert storage.reloads >= 2


def test_live_video_unknown_reel_is_404_not_a_signed_guess(monkeypatch):
    storage = _PresigningStorage()
    monkeypatch.setattr(api, "_storage", storage)
    live = TestClient(api.app)
    assert live.get("/reels/ghost/video", follow_redirects=False).status_code == 404
    assert storage.signed == []
