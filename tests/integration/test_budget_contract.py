"""The estimate a visitor reads must match what the server actually does.

The frontend tells someone their reel will take about six minutes. That is only
true because the backend runs the generation calls concurrently, five at a
time. The two numbers live in different languages and cannot import each other,
which is exactly the kind of pair that silently drifts: someone lowers the
backend's concurrency for a good reason, and the app carries on promising six
minutes for a reel that now takes half an hour.

So the contract is checked here, by reading the TypeScript source, rather than
trusted.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from cinemory import pipeline

BUDGET_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "reel-budget.ts"


def _const(name: str) -> int:
    source = BUDGET_TS.read_text(encoding="utf-8")
    match = re.search(rf"^export const {name} = (\d+);", source, re.MULTILINE)
    assert match, f"{name} is not a plain numeric constant in {BUDGET_TS.name} any more"
    return int(match.group(1))


@pytest.mark.skipif(not BUDGET_TS.exists(), reason="frontend sources not checked out")
def test_the_frontend_estimate_assumes_the_concurrency_the_backend_runs():
    assert _const("MAX_CONCURRENT_GENERATIONS") == pipeline.MAX_CONCURRENT_GENERATIONS


@pytest.mark.skipif(not BUDGET_TS.exists(), reason="frontend sources not checked out")
def test_a_full_reel_is_one_wave_of_calls():
    """The claim the six-minute estimate rests on: at the cap, every photo in
    a reel generates at the same time, so the reel costs one call's latency
    rather than five."""
    cap = _const("MAX_REEL_PHOTOS")
    assert cap <= pipeline.MAX_CONCURRENT_GENERATIONS, (
        f"a {cap}-photo reel needs more than one wave at concurrency "
        f"{pipeline.MAX_CONCURRENT_GENERATIONS}, so the frontend estimate is wrong"
    )


@pytest.mark.skipif(not BUDGET_TS.exists(), reason="frontend sources not checked out")
def test_the_server_still_accepts_more_photos_than_the_demo_offers():
    """The UI says the cap belongs to this demo and not to the reel maker.
    That has to stay true."""
    from cinemory.ingest import MAX_PHOTOS

    assert _const("MAX_REEL_PHOTOS") < MAX_PHOTOS
