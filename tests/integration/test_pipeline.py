from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.models import Bridge, Modality
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import sha256_bytes, verify_manifest
from cinemory.synthetic import synth_reel_spec


def _run(with_bridges=False):
    provider = FakeMediaProvider()
    storage = FakeStorage()
    spec = synth_reel_spec("demo", chapters=3, per_chapter=2)
    if with_bridges:
        for i in range(len(spec.chapters) - 1):
            spec.bridges.append(Bridge(spec.chapters[i].id, spec.chapters[i + 1].id, "bridge"))
    result = ReelPipeline(provider, storage).run(spec)
    return provider, storage, result


def test_one_video_step_per_photo():
    provider, _, result = _run()
    video_steps = [s for s in result.steps if s.modality.value == "video"]
    assert len(video_steps) == 6  # 3 chapters x 2 photos
    assert all(s.provider == "fake-genblaze" for s in result.steps)


def test_inputs_clips_reel_and_manifest_all_stored():
    _, storage, _ = _run()
    kinds = {row["key"].split("/")[1] for row in storage.index}
    assert {"photos", "clips", "reels", "manifests"} <= kinds


def test_bridges_add_steps():
    _, _, base = _run(with_bridges=False)
    _, _, bridged = _run(with_bridges=True)
    assert len(bridged.steps) == len(base.steps) + 2  # 2 chapter gaps


def test_manifest_persisted_and_verifiable():
    import json

    _, storage, result = _run()
    key = next(r["key"] for r in storage.index if r["key"].startswith("demo/manifests/"))
    manifest = json.loads(storage.get(key))
    assert verify_manifest(manifest) is True
    assert manifest["manifest_hash"] == result.manifest_hash


def test_reel_asset_hash_matches_stored_bytes():
    from cinemory.keys import KeyStrategy, make_key

    _, storage, result = _run()
    key = make_key(KeyStrategy.HIERARCHICAL, reel="demo", kind="reels",
                   sha256=result.reel_asset.sha256, name="reel.mp4")
    assert sha256_bytes(storage.get(key)) == result.reel_asset.sha256


def test_each_clip_step_cites_its_exact_source_photo():
    """Every one-photo clip step records exactly that photo's SHA-256, and the
    cited hash is the content anchor of the *persisted* input asset (its stored
    ``photos/`` key), not merely a recomputed digest."""
    spec = synth_reel_spec("cite", chapters=3, per_chapter=2)
    storage = FakeStorage()
    result = ReelPipeline(FakeMediaProvider(), storage).run(spec)

    flat_photos = [p for ch in spec.chapters for p in ch.photos]
    video_steps = [s for s in result.steps if s.modality is Modality.VIDEO]
    assert len(video_steps) == len(flat_photos) == 6

    # SHA-256 segments of the actually-persisted input photo assets.
    stored_photo_hashes = {
        seg
        for row in storage.index if "/photos/" in row["key"]
        for seg in row["key"].split("/") if len(seg) == 64
    }
    assert len(stored_photo_hashes) == 6

    # Step k was generated from flat_photos[k] (same nested chapter/photo order).
    for step, photo in zip(video_steps, flat_photos, strict=True):
        expected = sha256_bytes(photo.data)
        assert step.source_sha256s == [expected]        # exactly the one source
        assert expected in stored_photo_hashes          # cites the persisted asset


def test_bridge_step_cites_both_source_photos_in_input_order():
    """A first-last-frame bridge is built from two inputs — the last frame of the
    source chapter then the first of the target — so its citation records exactly
    those two hashes, order-stable."""
    spec = synth_reel_spec("bridge-cite", chapters=2, per_chapter=2)
    spec.bridges.append(Bridge(spec.chapters[0].id, spec.chapters[1].id, "bridge"))
    result = ReelPipeline(FakeMediaProvider(), FakeStorage()).run(spec)

    bridge_steps = [s for s in result.steps if s.params.get("kind") == "flf2v"]
    assert len(bridge_steps) == 1
    frm, to = spec.chapters[0], spec.chapters[1]
    assert bridge_steps[0].source_sha256s == [
        sha256_bytes(frm.photos[-1].data),
        sha256_bytes(to.photos[0].data),
    ]


def test_no_input_step_records_an_empty_citation():
    """A step generated from no inputs (e.g. a text-only step) leaves the
    citation empty — driven through the real ``_step`` population path."""
    pipe = ReelPipeline(FakeMediaProvider(), FakeStorage())
    rec = pipe._step(model="narrator", prompt="a text-only step", modality=Modality.TEXT,
                     inputs=[], params={}, reel="demo", kind="clips", name="text.mp4")
    assert rec.source_sha256s == []
