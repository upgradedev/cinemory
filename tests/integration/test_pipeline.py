from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.models import Bridge
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import verify_manifest
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
    from cinemory.provenance import sha256_bytes

    _, storage, result = _run()
    key = make_key(KeyStrategy.HIERARCHICAL, reel="demo", kind="reels",
                   sha256=result.reel_asset.sha256, name="reel.mp4")
    assert sha256_bytes(storage.get(key)) == result.reel_asset.sha256
