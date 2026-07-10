"""Parameterized end-to-end scenarios for Cinemory.

Generates exactly 50 distinct E2E test cases to verify the media compilation,
content-addressed hashing, and cryptographic provenance checks under various specs.
"""
import json
import pytest

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

# Generate 50 parameter combinations (index, chapters, per_chapter, strategy, tamper)
test_scenarios = []
for i in range(1, 51):
    # vary parameters deterministically
    chapters = 2 + (i % 3)
    per_chapter = 1 + (i % 2)
    tamper = (i % 7 == 0) # tamper in some test cases to verify failure detection
    test_scenarios.append((i, chapters, per_chapter, tamper))

@pytest.mark.parametrize("idx, chapters, per_chapter, tamper", test_scenarios)
def test_parameterized_e2e_journey(idx, chapters, per_chapter, tamper):
    storage = FakeStorage(bucket=f"cinemory-e2e-bucket-{idx}")
    spec = synth_reel_spec(f"scenario-reel-{idx}", chapters=chapters, per_chapter=per_chapter)
    
    # Connect chapters
    for c_idx in range(len(spec.chapters) - 1):
        spec.bridges.append(Bridge(spec.chapters[c_idx].id, spec.chapters[c_idx + 1].id, "fade"))

    # Run pipeline
    result = ReelPipeline(FakeMediaProvider(), storage).run(spec)

    # 1. Verification of content-addressable key (always HIERARCHICAL as utilized by ReelPipeline)
    reel_key = make_key(KeyStrategy.HIERARCHICAL, reel=f"scenario-reel-{idx}", kind="reels",
                        sha256=result.reel_asset.sha256, name="reel.mp4")
    reel_bytes = storage.get(reel_key)
    assert sha256_bytes(reel_bytes) == result.reel_asset.sha256

    # 2. Manifest verification
    manifest_key = next(r["key"] for r in storage.index
                        if r["key"].startswith(f"scenario-reel-{idx}/manifests/"))
    manifest = json.loads(storage.get(manifest_key))
    assert verify_manifest(manifest) is True

    # 3. Authenticity verification
    if tamper:
        # Alter the bytes to simulate tampering
        assert verify_asset(manifest, reel_key, reel_bytes + b"tampered_data") is False
    else:
        assert verify_asset(manifest, reel_key, reel_bytes) is True

    # 4. Durable asset step counts
    expected_steps = (chapters * per_chapter) + (chapters - 1)
    assert len(result.steps) == expected_steps
