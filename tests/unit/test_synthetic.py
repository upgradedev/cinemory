import io

from cinemory.synthetic import synth_photo, synth_reel_spec

# GMI Kling rejects any input whose shortest side is under 300px with
# ``Image pixel is invalid``. The old 512x288 default silently failed EVERY
# live synthetic run (POST /reels) at submit time; 1024x576 is the
# proven-working-live default (2026-07-22).
_KLING_MIN_SIDE = 300


def test_synth_photo_is_deterministic():
    a = synth_photo("x.png", seed=7)
    b = synth_photo("x.png", seed=7)
    assert a.data == b.data


def test_synth_photo_seed_changes_output():
    assert synth_photo("x.png", seed=1).data != synth_photo("x.png", seed=2).data


def test_synth_photo_is_valid_png():
    photo = synth_photo("x.png", seed=3)
    assert photo.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_reel_spec_shape():
    spec = synth_reel_spec("demo", chapters=3, per_chapter=2)
    assert spec.name == "demo"
    assert len(spec.chapters) == 3
    assert spec.photo_count() == 6
    assert all(c.prompt for c in spec.chapters)


def test_synth_photo_default_size_is_kling_compatible():
    from PIL import Image

    img = Image.open(io.BytesIO(synth_photo("x.png", seed=5).data))
    assert img.size == (1024, 576)
    assert min(img.size) >= _KLING_MIN_SIDE
    w, h = img.size
    assert w * 9 == h * 16  # 16:9 preserved


def test_reel_spec_photos_are_kling_compatible():
    """The exact live-failing path: POST /reels builds its photos through
    synth_reel_spec, so every spec photo must clear Kling's minimum side."""
    from PIL import Image

    spec = synth_reel_spec("demo", chapters=2, per_chapter=1)
    for chapter in spec.chapters:
        for photo in chapter.photos:
            img = Image.open(io.BytesIO(photo.data))
            assert min(img.size) >= _KLING_MIN_SIDE, (chapter.id, photo.filename)
