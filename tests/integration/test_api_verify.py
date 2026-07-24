"""Integration tests for ``GET /reels/{name}/verify`` — the server-side
aggregate named-check verification receipt.

Drives the real FastAPI app over the offline pipeline + FakeStorage: a sealed
reel verifies clean end-to-end, a store-level tamper flips the right check, an
unknown reel is a 404, and unreadable manifest bytes still return a fully-shaped
FAILING receipt (never a 500).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import cinemory.api as api

client = TestClient(api.app)


def _reel_key(name: str, *, suffix: str) -> str:
    from cinemory.keys import safe_component

    prefix = f"{safe_component(name)}/"
    return next(r["key"] for r in api._storage.index
               if r["key"].startswith(prefix) and r["key"].endswith(suffix))


def test_verify_reel_returns_a_passing_receipt():
    client.post("/reels", json={"name": "verifyme", "chapters": 2, "per_chapter": 1})
    r = client.get("/reels/verifyme/verify")
    assert r.status_code == 200
    receipt = r.json()
    assert set(receipt) == {"checks", "success", "digest"}
    assert receipt["success"] is True
    assert len(receipt["digest"]) == 64
    ids = {c["id"] for c in receipt["checks"]}
    assert {
        "seal.manifest_hash", "artifact.reel", "artifact.provenance_reel",
        "structural.embedded_manifest", "structural.step_assets_present",
        "structural.source_citation", "structural.provider_model",
    } <= ids
    # Two source photos → two per-step clips → two dynamic clip checks.
    assert {"artifact.clip.0", "artifact.clip.1"} <= ids
    for c in receipt["checks"]:
        assert set(c) == {"id", "label", "passed", "evidence"}
        assert c["passed"] is True


def test_verify_reel_flips_a_check_on_a_store_level_tamper():
    client.post("/reels", json={"name": "tamperme", "chapters": 2, "per_chapter": 1})
    # Swap the stored reel bytes in place (index row untouched → tamper signal).
    reel_key = _reel_key("tamperme", suffix="/reel.mp4")
    api._storage._objects[reel_key] = b"tampered-reel-bytes"

    receipt = client.get("/reels/tamperme/verify").json()
    assert receipt["success"] is False
    reel_check = next(c for c in receipt["checks"] if c["id"] == "artifact.reel")
    assert reel_check["passed"] is False
    # The seal (which reads only the manifest, not the swapped bytes) is intact.
    seal = next(c for c in receipt["checks"] if c["id"] == "seal.manifest_hash")
    assert seal["passed"] is True


def test_verify_unknown_reel_is_404():
    assert client.get("/reels/nope-not-here/verify").status_code == 404


def test_verify_reel_with_unreadable_manifest_returns_failing_receipt_not_500():
    client.post("/reels", json={"name": "brokenman", "chapters": 1, "per_chapter": 1})
    # Drop the manifest object but keep its index row → get() raises → the route
    # degrades to a fully-shaped FAILING receipt rather than a 500.
    man_key = _reel_key("brokenman", suffix="/manifest.json")
    del api._storage._objects[man_key]

    r = client.get("/reels/brokenman/verify")
    assert r.status_code == 200
    receipt = r.json()
    assert receipt["success"] is False
    seal = next(c for c in receipt["checks"] if c["id"] == "seal.manifest_hash")
    assert seal["passed"] is False
