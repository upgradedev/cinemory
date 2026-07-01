from cinemory.music import plan_beat_cuts


def test_cuts_are_deterministic():
    assert plan_beat_cuts(30.0, 120.0, 6) == plan_beat_cuts(30.0, 120.0, 6)


def test_cuts_cover_all_photos_in_order():
    cuts = plan_beat_cuts(30.0, 120.0, 6)
    assert [c.index for c in cuts] == [0, 1, 2, 3, 4, 5]
    assert all(c.end > c.start for c in cuts)


def test_cuts_stay_within_duration():
    cuts = plan_beat_cuts(20.0, 90.0, 4)
    assert all(0 <= c.start <= 20.0 and c.end <= 20.0 for c in cuts)


def test_degenerate_inputs_return_empty():
    assert plan_beat_cuts(0, 120, 4) == []
    assert plan_beat_cuts(30, 120, 0) == []


def test_zero_tempo_falls_back_to_even_split():
    cuts = plan_beat_cuts(12.0, 0.0, 3)
    assert len(cuts) == 3
