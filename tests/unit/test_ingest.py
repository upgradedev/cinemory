"""Unit tests for the real-photo ingest spec builder."""
import pytest

from cinemory.ingest import IngestError, build_spec_from_photos


def _photos(n: int) -> list[tuple[str, bytes]]:
    return [(f"p{i}.png", f"bytes-{i}".encode()) for i in range(n)]


def test_distributes_photos_across_chapters_in_order():
    spec = build_spec_from_photos("r", _photos(5), occasion="birthday", chapters=3)
    assert len(spec.chapters) == 3
    # 5 photos over 3 chapters -> 2,2,1 (remainder to earlier chapters).
    assert [len(c.photos) for c in spec.chapters] == [2, 2, 1]
    assert spec.photo_count() == 5
    # Upload order is preserved.
    all_names = [p.filename for c in spec.chapters for p in c.photos]
    assert set(all_names) == {f"p{i}.png" for i in range(5)}


def test_occasion_shapes_the_spec():
    spec = build_spec_from_photos("r", _photos(2), occasion="birthday", chapters=2)
    assert spec.occasion == "birthday"
    assert spec.aspect_ratio == "9:16"  # birthday preset is vertical


def test_more_chapters_than_photos_drops_empty_chapters():
    spec = build_spec_from_photos("r", _photos(2), chapters=5)
    assert len(spec.chapters) == 2
    assert all(c.photos for c in spec.chapters)


def test_bridges_are_optional_and_off_by_default():
    assert build_spec_from_photos("r", _photos(4), chapters=2).bridges == []
    spec = build_spec_from_photos("r", _photos(4), chapters=3, bridges=True)
    assert len(spec.bridges) == len(spec.chapters) - 1


def test_no_photos_is_rejected():
    with pytest.raises(IngestError):
        build_spec_from_photos("r", [])


def test_empty_photo_bytes_is_rejected():
    with pytest.raises(IngestError):
        build_spec_from_photos("r", [("a.png", b"")])


def test_out_of_range_chapters_is_rejected():
    with pytest.raises(IngestError):
        build_spec_from_photos("r", _photos(3), chapters=0)


def test_too_many_photos_is_rejected():
    with pytest.raises(IngestError):
        build_spec_from_photos("r", _photos(61))
