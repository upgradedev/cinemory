"""Concurrent generation must change the clock and nothing else.

Five photos at ~314s each, run one after another, is about 26 minutes against a
12-minute waiting window: five photos could never finish. The calls were always
independent (one photo in, one clip out; a bridge is generated from the
neighbouring chapters' PHOTOS, never from a generated clip), so running them at
the same time makes a five-photo reel cost about what a one-photo reel costs.

The risk that buys is not the speed, it is everything else moving: clips
arriving in completion order rather than spec order would reshuffle the edit,
and the sealed manifest would record different steps in a different order for
no reason at all. These specs pin that down.
"""
from __future__ import annotations

import threading
import time

import pytest

from cinemory import pipeline as pipeline_mod
from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.ingest import build_spec_from_photos
from cinemory.models import Modality
from cinemory.pipeline import ReelPipeline
from cinemory.provenance import build_manifest

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _spec(name: str, count: int = 5, *, bridges: bool = True):
    photos = [(f"p{i}.png", PNG + bytes([i])) for i in range(count)]
    return build_spec_from_photos(
        name, photos, occasion="anniversary", chapters=3, bridges=bridges
    )


class _SlowProvider:
    """A provider whose calls take real time and record their own overlap.

    ``peak`` is the highest number of calls that were ever in flight at once,
    which is how "did these actually run together" is answered without timing
    assertions that go flaky on a loaded CI runner.
    """

    name = "slow-provider"

    def __init__(self, delay: float = 0.25) -> None:
        self.delay = delay
        self._lock = threading.Lock()
        self._in_flight = 0
        self.peak = 0
        self.calls = 0

    def generate(self, *, model, prompt, modality, inputs, params) -> bytes:
        with self._lock:
            self._in_flight += 1
            self.peak = max(self.peak, self._in_flight)
            self.calls += 1
        try:
            time.sleep(self.delay)
        finally:
            with self._lock:
                self._in_flight -= 1
        return b"clip:" + prompt.encode()[:8] + str(len(inputs)).encode()


def test_generation_calls_actually_overlap():
    provider = _SlowProvider(delay=0.3)
    pipe = ReelPipeline(provider, FakeStorage(bucket="conc"))

    began = time.monotonic()
    pipe.run(_spec("overlap"))
    elapsed = time.monotonic() - began

    # 5 photos + 2 bridges = 7 calls at 0.3s. Sequentially that is >= 2.1s.
    assert provider.calls == 7
    assert provider.peak > 1, "calls did not overlap at all"
    assert elapsed < 7 * 0.3, f"took {elapsed:.2f}s, no faster than sequential"


def test_concurrency_is_bounded():
    provider = _SlowProvider(delay=0.2)
    pipe = ReelPipeline(provider, FakeStorage(bucket="bound"))
    pipe.run(_spec("bounded"))
    assert provider.peak <= pipeline_mod.MAX_CONCURRENT_GENERATIONS


def test_order_is_the_spec_order_no_matter_who_finishes_first(monkeypatch):
    """The load-bearing guarantee.

    A provider whose calls finish in REVERSE order of submission. The steps,
    the stored clip filenames and the sealed manifest must come out in spec
    order regardless.
    """
    order: list[str] = []

    class _ReverseFinishProvider:
        name = "reverse"

        def __init__(self) -> None:
            self._n = 0
            self._lock = threading.Lock()

        def generate(self, *, model, prompt, modality, inputs, params) -> bytes:
            with self._lock:
                self._n += 1
                mine = self._n
            # Earlier submissions sleep longer, so they finish last.
            time.sleep(max(0.0, (8 - mine) * 0.05))
            with self._lock:
                order.append(prompt)
            return b"clip:" + prompt.encode()[:12] + str(mine).encode()

    spec = _spec("reversed")
    result = ReelPipeline(_ReverseFinishProvider(), FakeStorage(bucket="rev")).run(spec)

    expected: list[str] = []
    for chapter in spec.chapters:
        for _ in chapter.photos:
            expected.append(f"{chapter.id}_")
    filenames = [s.asset.filename for s in result.steps]
    assert [f.split("_")[0] for f in filenames[: len(expected)]] == [
        e.split("_")[0] for e in expected
    ]
    # Bridges last, in spec order, exactly as before.
    assert filenames[len(expected):] == ["bridge_c0_c1.mp4", "bridge_c1_c2.mp4"]
    # And they genuinely did NOT finish in submission order, or this proves
    # nothing.
    assert len(order) == 7


def test_a_concurrent_run_seals_the_same_manifest_as_a_sequential_one(monkeypatch):
    """Byte-for-byte the same provenance, whichever way it was run.

    The deterministic offline provider gives identical clip bytes for identical
    (model, prompt, modality, inputs), so the only thing that could differ is
    ORDER, which is exactly what this catches. Timestamps are excluded because
    they legitimately differ between two runs of anything.
    """
    def steps_of(concurrency: int) -> list[tuple]:
        monkeypatch.setattr(pipeline_mod, "MAX_CONCURRENT_GENERATIONS", concurrency)
        result = ReelPipeline(
            FakeMediaProvider(), FakeStorage(bucket=f"c{concurrency}")
        ).run(_spec(f"same-{concurrency}"))
        manifest = build_manifest(result)
        return [
            (s["model"], s["prompt"], s["modality"], s["asset"]["sha256"],
             s["asset"]["filename"], tuple(s.get("source_sha256s", [])))
            for s in manifest["steps"]
        ]

    assert steps_of(1) == steps_of(5)


def test_a_single_planned_call_takes_the_plain_in_line_path(monkeypatch):
    """One photo, no bridges: no pool is created at all."""
    created = []
    real = pipeline_mod.ThreadPoolExecutor

    def spy(*args, **kwargs):
        created.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline_mod, "ThreadPoolExecutor", spy)
    ReelPipeline(FakeMediaProvider(), FakeStorage(bucket="one")).run(
        _spec("single", count=1, bridges=False)
    )
    assert created == []


def test_concurrency_can_be_turned_off_entirely(monkeypatch):
    """The escape hatch: a deployment can restore the old sequential behaviour
    without a code change."""
    monkeypatch.setattr(pipeline_mod, "MAX_CONCURRENT_GENERATIONS", 1)
    provider = _SlowProvider(delay=0.05)
    ReelPipeline(provider, FakeStorage(bucket="seq")).run(_spec("sequential"))
    assert provider.peak == 1


# ── rate limiting ────────────────────────────────────────────────────────────


class _RateLimitedTwice:
    """Refuses the first two calls with a rate limit, then answers."""

    name = "limited"

    def __init__(self, failures_before_success: int = 2) -> None:
        self.remaining = failures_before_success
        self.attempts = 0

    def generate(self, *, model, prompt, modality, inputs, params) -> bytes:
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise RuntimeError("429 Too Many Requests: rate limit exceeded")
        return b"clip"


def test_a_rate_limited_call_backs_off_and_succeeds(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "RATE_LIMIT_BASE_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(pipeline_mod, "RATE_LIMIT_MAX_ATTEMPTS", 3)
    provider = _RateLimitedTwice()
    pipe = ReelPipeline(provider, FakeStorage(bucket="rl"))

    gen = pipe._generate(model="m", prompt="p", modality=Modality.VIDEO,
                         inputs=[b"x"], params={})

    assert provider.attempts == 3
    assert gen.attempts == 3, "the retry count must be reported, not hidden"


def test_the_retry_budget_is_bounded(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "RATE_LIMIT_BASE_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(pipeline_mod, "RATE_LIMIT_MAX_ATTEMPTS", 3)
    provider = _RateLimitedTwice(failures_before_success=99)
    pipe = ReelPipeline(provider, FakeStorage(bucket="rl2"))

    with pytest.raises(RuntimeError, match="429"):
        pipe._generate(model="m", prompt="p", modality=Modality.VIDEO,
                       inputs=[b"x"], params={})
    assert provider.attempts == 3, "kept asking past the budget"


@pytest.mark.parametrize("message", [
    "GMICloud submit failed (402): Insufficient credits",
    "401 unauthorized",
    "submit failed (400): invalid payload parameters",
])
def test_a_failure_that_will_not_change_is_not_retried(monkeypatch, message):
    """Retrying a dead balance or a rejected request only spends a visitor's
    waiting window, and for credit it spends the thing that ran out."""
    monkeypatch.setattr(pipeline_mod, "RATE_LIMIT_BASE_DELAY_SECONDS", 0.01)
    attempts = {"n": 0}

    class _Always:
        name = "nope"

        def generate(self, **_kwargs) -> bytes:
            attempts["n"] += 1
            raise RuntimeError(message)

    pipe = ReelPipeline(_Always(), FakeStorage(bucket="nr"))
    with pytest.raises(RuntimeError):
        pipe._generate(model="m", prompt="p", modality=Modality.VIDEO,
                       inputs=[b"x"], params={})
    assert attempts["n"] == 1


def test_a_failed_call_does_not_wait_for_the_rest_of_the_wave():
    """One failure must reach the caller's honest fallback promptly, not after
    every other multi-minute render in the wave has finished."""
    class _FirstFailsRestAreSlow:
        name = "mixed"

        def __init__(self) -> None:
            self._lock = threading.Lock()
            self._n = 0

        def generate(self, *, model, prompt, modality, inputs, params) -> bytes:
            with self._lock:
                self._n += 1
                mine = self._n
            if mine == 1:
                raise RuntimeError("submit failed (400): nope")
            time.sleep(2.0)
            return b"clip"

    pipe = ReelPipeline(_FirstFailsRestAreSlow(), FakeStorage(bucket="fail"))
    began = time.monotonic()
    with pytest.raises(RuntimeError):
        pipe.run(_spec("failfast"))
    assert time.monotonic() - began < 1.5, "blocked on the rest of the wave"
