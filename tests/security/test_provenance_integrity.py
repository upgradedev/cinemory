"""PEN-TEST — Provenance integrity (the product's core security claim).

Cinemory's promise is a tamper-evident, SHA-256-sealed provenance manifest. This
suite is the adversarial view of that promise: every attempt to forge or tamper
with a sealed asset or manifest MUST be detected. It extends the tamper-evidence
unit tests into an attacker frame — forging the seal, mutating a recorded hash,
swapping bytes, and corrupting the embedded manifest.
"""
from __future__ import annotations

import json

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import (
    build_manifest,
    embed,
    extract,
    sha256_bytes,
    verify_asset,
    verify_manifest,
)
from cinemory.synthetic import synth_reel_spec


def _sealed():
    storage = FakeStorage(bucket="pentest")
    result = ReelPipeline(FakeMediaProvider(), storage).run(
        synth_reel_spec("prov", chapters=2, per_chapter=1))
    return storage, result, build_manifest(result)


def test_fresh_manifest_verifies():
    _, _, manifest = _sealed()
    assert verify_manifest(manifest) is True


def test_mutating_any_recorded_hash_is_detected():
    _, _, manifest = _sealed()
    tampered = json.loads(json.dumps(manifest))
    tampered["reel_asset"]["sha256"] = "0" * 64
    assert verify_manifest(tampered) is False


def test_mutating_a_step_field_is_detected():
    _, _, manifest = _sealed()
    tampered = json.loads(json.dumps(manifest))
    tampered["steps"][0]["prompt"] = "attacker-rewritten prompt"
    assert verify_manifest(tampered) is False


def test_forging_a_source_photo_citation_is_detected():
    """The clip-to-source-photo binding is sealed: an attacker who rewrites which
    input photo a generated clip was made from (to launder a swapped source)
    cannot do so without breaking the manifest hash."""
    _, _, manifest = _sealed()
    tampered = json.loads(json.dumps(manifest))
    cited = next(s for s in tampered["steps"] if s["source_sha256s"])
    cited["source_sha256s"][0] = "0" * 64  # forge the cited source photo
    assert verify_manifest(tampered) is False


def test_forged_seal_over_tampered_body_is_still_rejected():
    """An attacker who mutates a field and *recomputes a plausible-looking* seal
    over only the visible fields cannot forge the manifest: recompute over the
    real body still diverges. Here we forge a random 64-hex seal and confirm it
    fails; the seal is a function of the full body, not attacker-assertable."""
    _, _, manifest = _sealed()
    forged = json.loads(json.dumps(manifest))
    forged["occasion"] = "wedding"          # change the sealed content
    forged["manifest_hash"] = "f" * 64      # forge a seal
    assert verify_manifest(forged) is False


def test_stripping_the_seal_fails_closed():
    _, _, manifest = _sealed()
    stripped = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    assert verify_manifest(stripped) is False
    manifest["manifest_hash"] = ""
    assert verify_manifest(manifest) is False


def test_swapped_asset_bytes_fail_asset_verification():
    _, _, manifest = _sealed()
    assert verify_asset(manifest, "any", b"totally-different-bytes") is False


def test_stored_reel_bytes_match_the_sealed_hash():
    storage, result, _ = _sealed()
    reel_key = next(r["key"] for r in storage.index
                    if r["key"].startswith("prov/reels/") and r["key"].endswith("reel.mp4"))
    assert sha256_bytes(storage.get(reel_key)) == result.reel_asset.sha256


def test_embedded_manifest_is_recoverable_and_tamper_evident():
    storage, _, manifest = _sealed()
    prov_key = next(r["key"] for r in storage.index
                    if r["key"].endswith("reel.provenance.mp4"))
    container = storage.get(prov_key)
    recovered = extract(container)
    assert recovered is not None and verify_manifest(recovered) is True

    # Tamper with the embedded manifest bytes -> recovered seal must break.
    corrupted = extract(embed(b"VIDEO", {**recovered, "occasion": "evil"}))
    assert verify_manifest(corrupted) is False


def test_appending_a_second_manifest_cannot_shadow_the_real_one_silently():
    """``extract`` reads the *last* trailing manifest; if an attacker appends a
    forged one, its seal must still fail verification (it cannot forge a valid
    seal without the real body)."""
    _, _, manifest = _sealed()
    good = embed(b"VIDEO", manifest)
    attacker = extract(good)
    attacker["reel_name"] = "hijacked"      # forge content
    doctored = embed(good, attacker)        # append a second, forged manifest
    recovered = extract(doctored)
    assert recovered["reel_name"] == "hijacked"
    assert verify_manifest(recovered) is False  # forged seal is rejected
