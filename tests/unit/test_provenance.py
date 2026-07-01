from cinemory.models import Asset, Modality, ReelResult, StepRecord
from cinemory.provenance import (
    build_manifest,
    embed,
    extract,
    sha256_bytes,
    verify_asset,
    verify_manifest,
)


def _result() -> ReelResult:
    asset = Asset(modality=Modality.VIDEO, sha256=sha256_bytes(b"reel"), size_bytes=4,
                  url="b2://b/reel.mp4", filename="reel.mp4")
    step = StepRecord(provider="fake", model="m", prompt="p", modality=Modality.VIDEO,
                      params={"a": 1}, started_at="t0", finished_at="t1", asset=asset)
    return ReelResult(reel_name="r", reel_asset=asset, steps=[step])


def test_sha256_matches_hashlib():
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_manifest_builds_and_verifies():
    m = build_manifest(_result())
    assert m["manifest_hash"]
    assert verify_manifest(m) is True


def test_manifest_tamper_is_detected():
    m = build_manifest(_result())
    m["reel_asset"]["sha256"] = "0" * 64  # forge a hash
    assert verify_manifest(m) is False


def test_missing_hash_fails_verification():
    m = build_manifest(_result())
    del m["manifest_hash"]
    assert verify_manifest(m) is False


def test_verify_asset_matches_recorded_hash():
    r = _result()
    m = build_manifest(r)
    assert verify_asset(m, "any-key", b"reel") is True
    assert verify_asset(m, "any-key", b"tampered") is False


def test_embed_extract_roundtrip():
    m = build_manifest(_result())
    container = b"\x00\x01BINARYVIDEO\xff"
    blob = embed(container, m)
    assert blob.startswith(container)
    recovered = extract(blob)
    assert recovered == m
    assert verify_manifest(recovered) is True


def test_extract_returns_none_when_absent():
    assert extract(b"no manifest here") is None
