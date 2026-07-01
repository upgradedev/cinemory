import pytest

from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.models import Modality
from cinemory.ports import MediaProvider, StorageBackend
from cinemory.stitch import FakeStitcher


def test_fake_provider_is_deterministic_and_sized():
    p = FakeMediaProvider(clip_size=2048)
    a = p.generate(model="m", prompt="p", modality=Modality.VIDEO, inputs=[b"img"])
    b = p.generate(model="m", prompt="p", modality=Modality.VIDEO, inputs=[b"img"])
    assert a == b
    assert len(a) == 2048


def test_fake_provider_varies_with_prompt():
    p = FakeMediaProvider()
    a = p.generate(model="m", prompt="one", modality=Modality.VIDEO)
    b = p.generate(model="m", prompt="two", modality=Modality.VIDEO)
    assert a != b


def test_fake_provider_satisfies_port():
    assert isinstance(FakeMediaProvider(), MediaProvider)


def test_fake_storage_put_get_exists():
    s = FakeStorage(bucket="b")
    url = s.put("k/x", b"data", content_type="image/png")
    assert url == "b2://b/k/x"
    assert s.exists("k/x") is True
    assert s.get("k/x") == b"data"
    assert s.exists("missing") is False


def test_fake_storage_get_missing_raises():
    with pytest.raises(KeyError):
        FakeStorage().get("nope")


def test_fake_storage_index_and_jsonl():
    s = FakeStorage()
    s.put("a", b"1")
    s.put("b", b"22")
    assert len(s.index) == 2
    assert s.index_jsonl().count("\n") == 1
    assert isinstance(s, StorageBackend)


def test_fake_stitcher_is_deterministic_and_frames_clips():
    st = FakeStitcher()
    out1 = st.stitch([b"aa", b"bbb"])
    out2 = st.stitch([b"aa", b"bbb"])
    assert out1 == out2
    assert out1.startswith(b"MRREEL01")
    # both clips are recoverable in the framing -> length grows with content
    assert len(out1) > len(b"aa") + len(b"bbb")
