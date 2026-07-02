import pytest

from cinemory.occasions import (
    DEFAULT_OCCASION,
    OCCASIONS,
    get_occasion,
    list_occasions,
    resolve_key,
)
from cinemory.synthetic import synth_reel_spec

EXPECTED_KEYS = {
    "anniversary",
    "graduation",
    "birthday",
    "wedding",
    "year-in-review",
    "business-event",
}


def test_all_expected_presets_present():
    assert EXPECTED_KEYS.issubset(OCCASIONS.keys())


def test_default_is_anniversary():
    assert DEFAULT_OCCASION == "anniversary"
    assert get_occasion(None).key == "anniversary"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("award-ceremony", "business-event"),
        ("business-event/award-ceremony", "business-event"),
        ("YEAR-IN-REVIEW", "year-in-review"),
        ("year_in_review", "year-in-review"),
        ("  Wedding  ", "wedding"),
        ("nonsense", "anniversary"),  # unknown -> default
        (None, "anniversary"),
    ],
)
def test_resolve_key_normalises_and_aliases(raw, expected):
    assert resolve_key(raw) == expected


def test_style_prompt_appends_direction():
    occ = get_occasion("birthday")
    styled = occ.style_prompt("bright saturated shot,")
    assert styled.startswith("bright saturated shot")
    assert occ.prompt_direction in styled


def test_list_occasions_is_serialisable_catalogue():
    cat = list_occasions()
    assert {o["key"] for o in cat} == set(OCCASIONS.keys())
    for o in cat:
        assert isinstance(o["tempo"], float)
        assert o["label"] and o["aspect_ratio"]


def test_occasion_flows_into_spec():
    spec = synth_reel_spec("grad", chapters=2, per_chapter=1, occasion="graduation")
    assert spec.occasion == "graduation"
    assert spec.aspect_ratio == get_occasion("graduation").aspect_ratio
    # Scene labels + prompt direction from the preset propagate to chapters.
    occ = get_occasion("graduation")
    assert spec.chapters[0].label in occ.scene_labels
    assert occ.prompt_direction in spec.chapters[0].prompt


def test_unknown_occasion_falls_back_without_error():
    spec = synth_reel_spec("x", chapters=1, per_chapter=1, occasion="does-not-exist")
    assert spec.occasion == "anniversary"
