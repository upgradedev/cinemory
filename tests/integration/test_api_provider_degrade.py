"""Per-request provider degrade: a live-provider failure must never 500.

``test_api_live_degrade.py`` covers the *boot-time* contract (live mode with no
credentials wires the offline fakes). This file covers the *runtime* contract:
the live provider is wired and healthy at boot but a request fails mid-flight
(e.g. an upstream 400/timeout). The API must regenerate THAT request with the
offline provider against the same storage and say so honestly — a degraded
``200`` whose body carries ``provider_degraded: true`` plus the provider that
actually generated, with the sealed manifest recording the same provider on
every step. Nothing lies; nothing 500s for a remote-backend reason.
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

import cinemory.api as api
from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.pipeline import ReelPipeline


class _ExplodingLiveProvider:
    """Stands in for the live Genblaze adapter failing mid-request."""

    name = "genblaze"

    def generate(self, **_kwargs) -> bytes:
        raise RuntimeError("GMICloud submit failed (400): invalid payload parameters")


class _RealVideoOnlyStitcher:
    """Stands in for the live ``FfmpegStitcher``: real video tooling cannot
    decode the offline provider's deterministic clip bytes, so the degrade
    path must NOT inherit the live pipeline's stitcher."""

    name = "ffmpeg-stitcher"

    def stitch(self, clips: list[bytes]) -> bytes:
        raise RuntimeError("cannot decode non-video clip bytes")


@pytest.fixture
def degrade_client(monkeypatch):
    """The API wired like the live box: a provider that fails on every generate
    call AND a stitcher that only accepts real video (the harshest degrade
    configuration)."""
    storage = FakeStorage(bucket="degrade-test")
    monkeypatch.setattr(api, "_storage", storage)
    monkeypatch.setattr(
        api,
        "_pipeline",
        ReelPipeline(_ExplodingLiveProvider(), storage, stitcher=_RealVideoOnlyStitcher()),
    )
    return TestClient(api.app)


def test_live_provider_failure_degrades_to_200_with_honest_flags(degrade_client):
    r = degrade_client.post("/reels", json={"name": "boom", "chapters": 2, "per_chapter": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is True
    assert body["provider"] == "fake-genblaze"
    assert body["degrade_reason"] == "RuntimeError"
    # The degraded reel is still a real sealed reel.
    assert len(body["reel_sha256"]) == 64
    assert body["manifest_hash"]
    assert body["steps"] == 2
    # The sealed manifest records the provider that ACTUALLY generated.
    manifest = degrade_client.get("/reels/boom").json()
    assert manifest["steps"]
    assert all(s["provider"] == "fake-genblaze" for s in manifest["steps"])


def test_upload_path_degrades_too(degrade_client):
    photos = [{"filename": "p.png", "content_base64": base64.b64encode(b"px-bytes").decode()}]
    r = degrade_client.post("/reels/upload", json={"name": "boom-up", "photos": photos})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is True
    assert body["provider"] == "fake-genblaze"
    assert len(body["reel_sha256"]) == 64


def test_ingest_400_is_not_swallowed_by_degrade(degrade_client):
    """Client errors stay client errors — degrade only covers provider failures."""
    r = degrade_client.post("/reels/upload", json={"name": "empty", "photos": []})
    assert r.status_code == 400


def test_healthy_pipeline_reports_not_degraded():
    client = TestClient(api.app)  # module default: offline fakes
    r = client.post("/reels", json={"name": "ok-flag", "chapters": 1, "per_chapter": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is False
    assert body["provider"] == "fake-genblaze"


def test_offline_provider_failure_is_a_real_500(monkeypatch):
    """Degrade masks only LIVE provider failures; the offline fake failing is a
    genuine bug and must surface, not be retried into a lie."""

    class _BrokenFake(FakeMediaProvider):
        def generate(self, **_kwargs) -> bytes:
            raise RuntimeError("offline provider bug")

    storage = FakeStorage(bucket="bug")
    monkeypatch.setattr(api, "_storage", storage)
    monkeypatch.setattr(api, "_pipeline", ReelPipeline(_BrokenFake(), storage))
    client = TestClient(api.app, raise_server_exceptions=False)
    r = client.post("/reels", json={"name": "bug", "chapters": 1, "per_chapter": 1})
    assert r.status_code == 500
