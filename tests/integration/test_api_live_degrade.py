"""The core action must survive a credential-free ``live`` deployment.

The live Cloud Run container can be started with ``CINEMORY_MODE=live`` but no
B2/GMI credentials. The API builds its storage + provider at *import time*, so a
naive live path would crash on import (or 500 on the first request). This test
reloads the API module under exactly that hostile environment and asserts the
whole flow still works: ``POST /reels`` returns 200 with a real deterministic
reel + sealed SHA-256 manifest, and ``/health`` honestly reports the degraded
backends.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

_B2_ENV = (
    "B2_KEY_ID", "B2_APP_KEY", "B2_ENDPOINT_URL", "B2_REGION", "B2_BUCKET_NAME",
    "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY", "B2_S3_ENDPOINT",
    "B2_KEY_PREFIX", "B2_PREFIX", "GMI_API_KEY",
)


@pytest.fixture
def live_no_creds_client(monkeypatch):
    """Reload the API with live mode requested but zero credentials present."""
    monkeypatch.setenv("CINEMORY_MODE", "live")
    for name in _B2_ENV:
        monkeypatch.delenv(name, raising=False)

    import cinemory.api as api

    reloaded = importlib.reload(api)
    try:
        yield TestClient(reloaded.app)
    finally:
        # Restore the module to its default (offline) state so live-degraded
        # wiring never leaks into other tests that import cinemory.api.
        monkeypatch.delenv("CINEMORY_MODE", raising=False)
        importlib.reload(api)


def test_post_reels_never_500s_without_creds(live_no_creds_client):
    r = live_no_creds_client.post("/reels", json={"name": "livedemo", "chapters": 2,
                                                  "per_chapter": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["reel_sha256"]) == 64
    assert body["manifest_hash"]
    assert body["steps"] == 4


def test_upload_also_works_without_creds(live_no_creds_client):
    import base64
    photos = [{"filename": "p.png", "content_base64": base64.b64encode(b"px").decode()}]
    r = live_no_creds_client.post("/reels/upload", json={"name": "liveup", "photos": photos})
    assert r.status_code == 200
    assert len(r.json()["reel_sha256"]) == 64


def test_health_reports_degraded_backends(live_no_creds_client):
    body = live_no_creds_client.get("/health").json()
    # Requested mode is honest (live)…
    assert body["mode"] == "live"
    # …but the effective backends degraded to the offline fakes.
    assert body["provider"] == "fake-genblaze"
    assert body["storage"] == "FakeStorage"
