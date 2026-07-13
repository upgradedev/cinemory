"""PEN-TEST — Sensitive-data exposure.

Threat: credentials/keys leak into an API response, an error body, a log line, or
the sealed manifest — including on the offline-degrade path (live mode, missing
creds). The invariant: a seeded sentinel credential value appears in NONE of
those surfaces.
"""
from __future__ import annotations

import base64
import json
import logging
import os

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import build_manifest
from cinemory.synthetic import synth_reel_spec

from .conftest import fresh_client

_SENTINEL = "SENTINEL-SECRET-DO-NOT-LEAK-abc123"


def test_health_does_not_expose_credentials(client):
    body = client.get("/health").json()
    blob = json.dumps(body).lower()
    assert _SENTINEL.lower() not in blob
    # /health surfaces only mode + backend class names, never secret material.
    assert set(body) >= {"status", "service", "mode", "provider", "storage"}
    assert "b2_" not in blob and "gmi" not in blob


def test_manifest_contains_no_credentials():
    storage = FakeStorage(bucket="pentest")
    result = ReelPipeline(FakeMediaProvider(), storage).run(
        synth_reel_spec("nocreds", chapters=2, per_chapter=1))
    manifest_blob = json.dumps(build_manifest(result)).lower()
    for banned in ("secret", "password", "b2_app_key", "aws_secret", "api_key"):
        assert banned not in manifest_blob


def test_offline_degrade_path_leaks_no_seeded_secret(caplog, scrub_credentials):
    """Live mode with a *partial/misconfigured* credential set (a key present but
    insufficient config) must degrade to the offline fakes and leak the seeded
    secret NOWHERE — not in the response body, not in logs (even at DEBUG).
    Covers 'offline-degrade path leaks nothing' + 'no creds in logs' at once.

    We seed only the B2 key material (bucket/endpoint intentionally absent → the
    B2 backend is not ready → degrade) and leave the provider unconfigured, so
    both backends fall back to fakes regardless of which optional SDKs are
    installed — and the seeded secret is nonetheless present in the environment.
    """
    for var in ("B2_KEY_ID", "B2_APP_KEY", "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY"):
        os.environ[var] = _SENTINEL
    client, restore = fresh_client(mode="live")
    try:
        with caplog.at_level(logging.DEBUG):
            r = client.post("/reels", json={"name": "degrade", "chapters": 2,
                                            "per_chapter": 2})
            health = client.get("/health").json()
        assert r.status_code == 200                     # never 500s
        assert _SENTINEL not in r.text
        assert _SENTINEL not in json.dumps(health)
        assert _SENTINEL not in caplog.text             # not logged, even at DEBUG
        # It genuinely degraded (proves we exercised the no-usable-creds path).
        assert health["storage"] == "FakeStorage"
        assert health["provider"] == "fake-genblaze"
    finally:
        for var in ("B2_KEY_ID", "B2_APP_KEY", "B2_APPLICATION_KEY_ID", "B2_APPLICATION_KEY"):
            os.environ.pop(var, None)
        restore()


def test_error_response_does_not_echo_internal_paths_or_secrets(client):
    """A 400 body carries a user-facing message, not a stack trace / secret."""
    r = client.post("/reels/upload", json={
        "name": "err", "photos": [{"filename": "p.png",
                                    "content_base64": base64.b64encode(b"").decode()}]})
    assert r.status_code == 400
    assert _SENTINEL not in r.text
    assert "Traceback" not in r.text and "site-packages" not in r.text
