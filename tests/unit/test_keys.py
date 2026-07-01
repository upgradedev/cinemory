from cinemory.keys import KeyStrategy, make_key


def test_hierarchical_key_layout():
    key = make_key(KeyStrategy.HIERARCHICAL, reel="demo", kind="clips",
                   sha256="abcdef0123456789", name="c0_p0.mp4")
    assert key == "demo/clips/ab/abcdef0123456789/c0_p0.mp4"


def test_flat_key_layout():
    key = make_key(KeyStrategy.FLAT, reel="demo", kind="clips",
                   sha256="abcdef", name="c0.mp4")
    assert key == "abcdef-c0.mp4"


def test_content_addressing_dedupes_identical_bytes():
    a = make_key(KeyStrategy.HIERARCHICAL, reel="d", kind="clips", sha256="ff00", name="x")
    b = make_key(KeyStrategy.HIERARCHICAL, reel="d", kind="clips", sha256="ff00", name="x")
    assert a == b
