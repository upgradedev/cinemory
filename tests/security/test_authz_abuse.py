"""PEN-TEST — AuthZ / abuse / resource exhaustion.

Threat: a caller sends oversized, malformed, or resource-amplifying uploads to
crash the worker (5xx), exhaust memory, or bypass the ingest guardrails. The API
must reject every one of these at the boundary with a 4xx and never 5xx.
"""
from __future__ import annotations

import base64

from cinemory.ingest import MAX_CHAPTERS, MAX_PHOTOS

from .conftest import PNG_1x1


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_over_max_photos_is_rejected_4xx(client):
    """MAX_PHOTOS is enforced: one over the cap is a clean 400, not an OOM/5xx."""
    photos = [{"filename": f"p{i}.png", "content_base64": _b64(PNG_1x1)}
              for i in range(MAX_PHOTOS + 1)]
    r = client.post("/reels/upload", json={"name": "abuse-max", "photos": photos})
    assert r.status_code == 400
    assert r.status_code < 500


def test_over_max_photos_multipart_is_rejected_4xx(client):
    """Same cap enforced on the multipart (raw-bytes) upload surface."""
    files = [("files", (f"p{i}.png", PNG_1x1, "image/png")) for i in range(MAX_PHOTOS + 1)]
    r = client.post("/reels/upload-multipart", files=files, data={"name": "abuse-max-mp"})
    assert 400 <= r.status_code < 500


def test_unbounded_chapters_is_rejected_4xx(client):
    """A huge ``chapters`` count (resource amplification) is bounded, not honoured."""
    r = client.post("/reels/upload", json={
        "name": "abuse-chapters", "chapters": 10_000_000,
        "photos": [{"filename": "p.png", "content_base64": _b64(PNG_1x1)}]})
    assert r.status_code == 400
    assert MAX_CHAPTERS < 10_000_000  # the guardrail is what bounds it


def test_empty_photo_bytes_is_rejected_4xx(client):
    r = client.post("/reels/upload", json={
        "name": "abuse-empty",
        "photos": [{"filename": "p.png", "content_base64": ""}]})
    assert 400 <= r.status_code < 500


def test_malformed_multipart_missing_files_is_4xx_not_5xx(client):
    """A multipart request with no ``files`` part is a 4xx validation error."""
    r = client.post("/reels/upload-multipart", data={"name": "no-files"})
    assert 400 <= r.status_code < 500


def test_malformed_base64_is_4xx_not_5xx(client):
    r = client.post("/reels/upload", json={
        "name": "abuse-b64",
        "photos": [{"filename": "p.png", "content_base64": "not!valid!base64!!"}]})
    assert r.status_code == 400


def test_wrong_type_chapters_is_4xx_not_5xx(client):
    """A non-integer ``chapters`` is a 422 (pydantic), never a 500."""
    r = client.post("/reels/upload", json={
        "name": "abuse-type", "chapters": "lots",
        "photos": [{"filename": "p.png", "content_base64": _b64(PNG_1x1)}]})
    assert 400 <= r.status_code < 500


def test_no_photos_is_rejected_4xx(client):
    r = client.post("/reels/upload", json={"name": "abuse-none", "photos": []})
    assert r.status_code == 400
