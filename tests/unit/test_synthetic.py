from cinemory.synthetic import synth_photo, synth_reel_spec


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
