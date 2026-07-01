"""Music-driven cut planning.

``plan_beat_cuts`` is a pure, deterministic function (unit-tested, no deps) that
distributes N photos across a track so scene changes land on musical beats.

``analyze_music`` is the optional real path: librosa beat + segment analysis
(concept ported from cinemory). It is import-guarded so the package stays
installable and CI stays green without the heavy audio stack.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cut:
    index: int
    start: float
    end: float


def plan_beat_cuts(duration: float, tempo: float, n_photos: int) -> list[Cut]:
    """Assign each photo an on-beat time window across ``duration`` seconds.

    Deterministic: identical inputs -> identical cuts. Falls back gracefully
    for degenerate inputs (no photos, non-positive tempo/duration).
    """
    if n_photos <= 0 or duration <= 0:
        return []
    beat_len = 60.0 / tempo if tempo > 0 else duration / n_photos
    # Evenly spread photos across the timeline, snapping each boundary to the
    # nearest beat so transitions feel musical.
    cuts: list[Cut] = []
    for i in range(n_photos):
        raw_start = duration * i / n_photos
        raw_end = duration * (i + 1) / n_photos
        start = round(round(raw_start / beat_len) * beat_len, 3) if beat_len else raw_start
        end = round(round(raw_end / beat_len) * beat_len, 3) if beat_len else raw_end
        if end <= start:
            end = round(start + beat_len, 3)
        cuts.append(Cut(index=i, start=min(start, duration), end=min(end, duration)))
    return cuts


def analyze_music(audio_path: str) -> dict:  # pragma: no cover - optional heavy path
    """Real beat/segment analysis via librosa. Optional dependency."""
    try:
        import librosa  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("librosa is required for analyze_music: pip install librosa") from exc
    import numpy as np

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    duration = len(y) / sr
    tempo_arr, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(np.atleast_1d(tempo_arr)[0])
    beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    return {"duration": round(duration, 2), "tempo": round(tempo, 1),
            "beats": [round(float(b), 3) for b in beats]}
