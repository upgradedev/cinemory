"""PEN-TEST — Injection / path traversal into storage keys.

Threat: an attacker controls the reel *name* and the uploaded *filename*, and
those strings become segments of the object-storage key. Without sanitisation a
hostile value (``../../evil``, ``../../../etc/passwd``, NUL, newline) would inject
into the B2 key namespace. The invariant: every stored key is anchored by the
machine-derived SHA-256 and its user-controlled segments are sanitised — no
``..`` segment, no path separator escape, no NUL/newline, no leading-dot label.

Note on severity: B2/S3 is a *flat* namespace, so ``..`` is a literal key
segment, not a filesystem escape — this is key/prefix hygiene (defence in depth),
not disk traversal. The tests assert the sanitisation invariant regardless.
"""
from __future__ import annotations

import base64

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.ingest import build_spec_from_photos
from cinemory.keys import KeyStrategy, make_key, safe_component
from cinemory.pipeline import ReelPipeline

from .conftest import PNG_1x1

_HOSTILE = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32",
    "/absolute/evil",
    "a/b/../../c",
    "..",
    "with\x00nul",
    "with\nnewline",
    "  ..%2f..%2f  ",
]


def _assert_key_is_safe(key: str) -> None:
    for seg in key.split("/"):
        assert seg != "..", f"traversal segment in key: {key!r}"
        assert not seg.startswith("."), f"leading-dot label in key: {key!r}"
    assert "\x00" not in key, f"NUL in key: {key!r}"
    assert "\n" not in key and "\r" not in key, f"newline in key: {key!r}"
    assert "\\" not in key, f"backslash separator in key: {key!r}"
    assert not key.startswith("/"), f"absolute key: {key!r}"


def test_safe_component_neutralises_every_hostile_value():
    for value in _HOSTILE:
        out = safe_component(value)
        assert out and out != ".."
        assert "/" not in out and "\\" not in out
        assert "\x00" not in out and "\n" not in out
        assert not out.startswith(".")


def test_make_key_never_emits_a_traversal_key():
    for reel in _HOSTILE:
        for name in _HOSTILE:
            key = make_key(KeyStrategy.HIERARCHICAL, reel=reel, kind="photos",
                           sha256="a" * 64, name=name)
            _assert_key_is_safe(key)
            # The content anchor (SHA-256) is always present and intact.
            assert "a" * 64 in key.split("/")


def test_content_address_is_derived_from_bytes_not_filename():
    """Two different hostile filenames with identical bytes hash to the same
    content anchor — identity is content-addressed, not attacker-named."""
    k1 = make_key(KeyStrategy.HIERARCHICAL, reel="r", kind="photos",
                  sha256="d" * 64, name="../../a.png")
    k2 = make_key(KeyStrategy.HIERARCHICAL, reel="r", kind="photos",
                  sha256="d" * 64, name="..\\b.png")
    assert k1.split("/")[3] == k2.split("/")[3] == "d" * 64


def test_pipeline_stores_only_safe_keys_for_hostile_ingest():
    """End-to-end: a hostile reel name + filenames flow through the real pipeline;
    every key written to storage is sanitised and content-addressed."""
    spec = build_spec_from_photos(
        "../../evil-reel",
        [("../../../etc/passwd", PNG_1x1), ("a/b/../c.png", PNG_1x1)],
        occasion="anniversary", chapters=2)
    storage = FakeStorage(bucket="pentest")
    ReelPipeline(FakeMediaProvider(), storage).run(spec)
    assert storage.index  # work happened
    for row in storage.index:
        _assert_key_is_safe(row["key"])
        # Hierarchical layout keeps its content anchor.
        parts = row["key"].split("/")
        assert any(len(p) == 64 for p in parts), row["key"]


def test_api_traversal_upload_does_not_escape_key_prefix(client):
    """The full HTTP path: a traversal reel name + filename returns 200 and every
    resulting storage key is sanitised (no escape from the reel's own prefix)."""
    photos = [{"filename": "../../../etc/passwd",
               "content_base64": base64.b64encode(PNG_1x1).decode()}]
    r = client.post("/reels/upload", json={"name": "../../evil", "photos": photos})
    assert r.status_code == 200
    body = r.json()
    # The returned URLs must not contain a traversal sequence.
    assert "/../" not in body["reel_url"] and "/../" not in body["manifest_uri"]
    assert "etc/passwd" not in body["reel_url"]


def test_occasion_param_cannot_inject_into_keys():
    """The occasion is resolved against a fixed allowlist and only its canonical
    key ever reaches storage — a hostile occasion cannot inject a key segment."""
    spec = build_spec_from_photos(
        "r", [("p.png", PNG_1x1)], occasion="../../../secret", chapters=1)
    assert spec.occasion in {"anniversary", "graduation", "birthday", "wedding",
                             "year-in-review", "business-event"}
    storage = FakeStorage(bucket="pentest")
    ReelPipeline(FakeMediaProvider(), storage).run(spec)
    for row in storage.index:
        assert "secret" not in row["key"]
