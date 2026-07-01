"""End-to-end: synthetic memories -> AI reel -> Backblaze B2 (fake) -> provenance.

The whole journey runs offline, but every hash is real. The test reloads the
reel and manifest *from the store* (not from in-memory objects) and asserts on
SHA-256 values the provenance layer recomputes — so a green run proves the
pipeline actually produced and sealed what it claims.
"""
import json

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.keys import KeyStrategy, make_key
from cinemory.models import Bridge
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import (
    extract,
    sha256_bytes,
    verify_asset,
    verify_manifest,
)
from cinemory.synthetic import synth_reel_spec


def test_full_journey_with_verifiable_provenance():
    storage = FakeStorage(bucket="cinemory-e2e")
    spec = synth_reel_spec("anniversary-demo", chapters=3, per_chapter=2)
    # connect the chapters with first-last-frame bridges
    for i in range(len(spec.chapters) - 1):
        spec.bridges.append(Bridge(spec.chapters[i].id, spec.chapters[i + 1].id, "match cut"))

    result = ReelPipeline(FakeMediaProvider(), storage).run(spec)

    # 1. Reel is retrievable from B2 by its content-addressed key.
    reel_key = make_key(KeyStrategy.HIERARCHICAL, reel="anniversary-demo", kind="reels",
                        sha256=result.reel_asset.sha256, name="reel.mp4")
    reel_bytes = storage.get(reel_key)

    # 2. The stored bytes hash to exactly what the result/manifest recorded.
    assert sha256_bytes(reel_bytes) == result.reel_asset.sha256

    # 3. The manifest reloaded from B2 verifies (canonical hash intact).
    manifest_key = next(r["key"] for r in storage.index
                        if r["key"].startswith("anniversary-demo/manifests/"))
    manifest = json.loads(storage.get(manifest_key))
    assert verify_manifest(manifest) is True
    assert verify_asset(manifest, reel_key, reel_bytes) is True

    # 4. The embedded-provenance reel carries a manifest that still verifies.
    prov_key = next(r["key"] for r in storage.index
                    if r["key"].endswith("reel.provenance.mp4"))
    embedded = extract(storage.get(prov_key))
    assert embedded is not None
    assert verify_manifest(embedded) is True
    assert embedded["manifest_hash"] == result.manifest_hash

    # 5. Every generated step landed as a durable asset in B2.
    assert len(result.steps) == 6 + 2  # 6 clips + 2 bridges
    assert all(s.asset.url.startswith("b2://cinemory-e2e/") for s in result.steps)

    # 6. A tampered reel is rejected by the provenance check.
    assert verify_asset(manifest, reel_key, reel_bytes + b"tamper") is False


def test_cli_smoke(tmp_path, monkeypatch):
    monkeypatch.delenv("CINEMORY_MODE", raising=False)
    from cinemory.cli import main

    rc = main(["--name", "clidemo", "--chapters", "2", "--per-chapter", "1",
               "--bridges", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "reel.mp4").exists()
    assert (tmp_path / "manifest.json").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert verify_manifest(manifest) is True
