"""Unit tests for the aggregate named-check verification receipt.

``verify_all`` re-runs every provenance check from stored bytes and returns a
``VerificationReceipt``. These tests seal a real reel through the offline
pipeline, build a logical-name → bytes fetcher that mirrors the API's
``_artifact_fetcher`` scheme, and confirm (a) a good reel passes every check and
(b) each check flips to ``passed: false`` under a targeted tamper — plus that a
raising fetcher is fail-closed rather than crashing the receipt.
"""
from __future__ import annotations

import copy

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import (
    VerificationReceipt,
    build_manifest,
    embed,
    verify_all,
)
from cinemory.synthetic import synth_reel_spec


def _seal() -> tuple[dict, dict[str, bytes]]:
    """Seal a real reel offline and return ``(manifest, logical→bytes)``.

    The ``blob`` map mirrors the logical names ``verify_all`` asks its fetcher
    for (``reel``, ``provenance_reel``, ``clip:<sha>``, ``photo:<sha>``), built
    from the content-addressed keys the pipeline actually wrote.
    """
    storage = FakeStorage(bucket="verify")
    result = ReelPipeline(FakeMediaProvider(), storage).run(
        synth_reel_spec("verify-reel", chapters=2, per_chapter=1)
    )
    manifest = build_manifest(result)
    blob: dict[str, bytes] = {}
    for row in storage.index:
        key = row["key"]
        data = storage.get(key)
        parts = key.split("/")  # <reel>/<kind>/<shard>/<sha>/<name>
        if key.endswith("/reel.mp4"):
            blob["reel"] = data
        elif key.endswith("/reel.provenance.mp4"):
            blob["provenance_reel"] = data
        elif len(parts) >= 4 and parts[1] == "clips":
            blob[f"clip:{parts[3]}"] = data
        elif len(parts) >= 4 and parts[1] == "photos":
            blob[f"photo:{parts[3]}"] = data
    return manifest, blob


def _fetch(blob: dict[str, bytes]):
    return lambda logical: blob.get(logical)


def _ids(receipt: VerificationReceipt) -> set[str]:
    return {c["id"] for c in receipt.checks}


def _passed(receipt: VerificationReceipt, check_id: str) -> bool:
    return next(c["passed"] for c in receipt.checks if c["id"] == check_id)


# ── happy path ────────────────────────────────────────────────────────────────
def test_verify_all_passes_on_a_good_reel():
    manifest, blob = _seal()
    receipt = verify_all(manifest, _fetch(blob))
    assert receipt.success is True
    assert all(c["passed"] for c in receipt.checks)
    # The full named-check set, including the two dynamic per-step clip checks.
    assert {
        "seal.manifest_hash",
        "artifact.reel",
        "artifact.provenance_reel",
        "artifact.clip.0",
        "artifact.clip.1",
        "structural.embedded_manifest",
        "structural.step_assets_present",
        "structural.source_citation",
        "structural.provider_model",
    } <= _ids(receipt)
    # Each row is fully shaped.
    for c in receipt.checks:
        assert set(c) == {"id", "label", "passed", "evidence"}
        assert c["evidence"]


def test_receipt_digest_is_deterministic_and_content_addressed():
    manifest, blob = _seal()
    a = verify_all(manifest, _fetch(blob))
    b = verify_all(manifest, _fetch(blob))
    assert a.digest == b.digest and len(a.digest) == 64
    assert a.to_dict() == {"checks": a.checks, "success": True, "digest": a.digest}


# ── targeted tampers: each flips exactly the check it should ───────────────────
def test_seal_check_flips_when_manifest_hash_is_wrong():
    manifest, blob = _seal()
    tampered = copy.deepcopy(manifest)
    tampered["manifest_hash"] = "0" * 64  # only the seal depends on this
    receipt = verify_all(tampered, _fetch(blob))
    assert _passed(receipt, "seal.manifest_hash") is False
    assert _passed(receipt, "artifact.reel") is True  # isolated
    assert receipt.success is False


def test_artifact_reel_flips_when_stored_reel_bytes_are_swapped():
    manifest, blob = _seal()
    blob["reel"] = b"tampered-reel-bytes"
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "artifact.reel") is False
    assert _passed(receipt, "seal.manifest_hash") is True  # isolated


def test_artifact_provenance_reel_flips_when_it_wraps_a_different_reel():
    manifest, blob = _seal()
    # Same (correct) embedded manifest, but a DIFFERENT reel payload.
    blob["provenance_reel"] = embed(b"not-the-sealed-reel", manifest)
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "artifact.provenance_reel") is False
    assert _passed(receipt, "structural.embedded_manifest") is True  # isolated


def test_artifact_clip_flips_when_a_stored_clip_is_swapped():
    manifest, blob = _seal()
    clip_key = next(k for k in blob if k.startswith("clip:"))
    blob[clip_key] = b"tampered-clip"
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "artifact.clip.0") is False
    assert _passed(receipt, "seal.manifest_hash") is True


def test_embedded_manifest_flips_when_the_embedded_manifest_differs():
    manifest, blob = _seal()
    other = copy.deepcopy(manifest)
    other["reel_name"] = "someone-elses-reel"
    # Correct reel payload, but a DIFFERENT embedded manifest.
    blob["provenance_reel"] = embed(blob["reel"], other)
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "structural.embedded_manifest") is False
    assert _passed(receipt, "artifact.provenance_reel") is True  # isolated (reel payload intact)


def test_step_assets_present_flips_when_a_step_asset_is_dropped():
    manifest, blob = _seal()
    clip_key = next(k for k in blob if k.startswith("clip:"))
    del blob[clip_key]  # the store no longer holds this clip
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "structural.step_assets_present") is False
    assert _passed(receipt, "seal.manifest_hash") is True


def test_source_citation_flips_when_a_cited_photo_is_dropped():
    manifest, blob = _seal()
    photo_key = next(k for k in blob if k.startswith("photo:"))
    del blob[photo_key]  # a cited source photo is no longer resolvable
    receipt = verify_all(manifest, _fetch(blob))
    assert _passed(receipt, "structural.source_citation") is False
    assert _passed(receipt, "seal.manifest_hash") is True  # isolated: manifest untouched


def test_provider_model_flips_when_a_provider_is_stripped():
    manifest, blob = _seal()
    tampered = copy.deepcopy(manifest)
    tampered["steps"][0]["provider"] = ""  # strip the provider
    receipt = verify_all(tampered, _fetch(blob))
    assert _passed(receipt, "structural.provider_model") is False
    # The seal co-fails (provider lives only in the sealed manifest, so it can't
    # be isolated the way store-level tampers are) — that is expected.
    assert _passed(receipt, "seal.manifest_hash") is False


# ── robustness ────────────────────────────────────────────────────────────────
def test_verify_all_is_fail_closed_when_the_fetcher_raises():
    manifest, _ = _seal()

    def boom(_logical: str) -> bytes | None:
        raise RuntimeError("storage exploded")

    receipt = verify_all(manifest, boom)
    assert receipt.success is False
    # The seal check needs no fetch, so it still passes; artifact checks fail
    # closed with the exception surfaced as evidence — never a crash.
    assert _passed(receipt, "seal.manifest_hash") is True
    assert _passed(receipt, "artifact.reel") is False
    assert any("RuntimeError" in c["evidence"] for c in receipt.checks)


def test_verify_all_tolerates_a_non_dict_manifest():
    receipt = verify_all(None, lambda _l: None)  # type: ignore[arg-type]
    assert receipt.success is False
    assert _passed(receipt, "seal.manifest_hash") is False
