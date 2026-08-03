"""What one reel burned, measured and readable per job.

The owner needs to be able to say, after a demo, exactly what it consumed. The
numbers have to be real: every one of these comes from something that actually
happened during the run, and there is deliberately no money anywhere, because
reliable per-call pricing is not available to us and an invented euro figure
would look authoritative and be wrong.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

import cinemory.api as api
from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.ingest import build_spec_from_photos
from cinemory.pipeline import ReelPipeline
from cinemory.usage import RunUsage

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _run(name: str, count: int = 3, *, bridges: bool = True):
    photos = [(f"p{i}.png", PNG + bytes([i]) * (i + 1)) for i in range(count)]
    spec = build_spec_from_photos(
        name, photos, occasion="anniversary", chapters=2, bridges=bridges
    )
    return ReelPipeline(FakeMediaProvider(), FakeStorage(bucket="usage")).run(spec)


def test_every_provider_call_is_counted_and_attributed_to_its_model():
    result = _run("counted", count=3)
    usage = result.usage
    assert usage is not None

    # 3 photos + 1 bridge (2 chapters) = 4 calls, and the breakdown names the
    # models rather than lumping them together.
    assert len(usage.calls) == 4
    assert usage.calls_by_model == {
        "Kling-Image2Video-V2.1-Master": 3,
        "seedance-2-0-260128": 1,
    }
    assert sum(usage.calls_by_model.values()) == len(usage.calls)


def test_wall_clock_is_recorded_per_call_and_for_the_run():
    result = _run("clocked", count=2, bridges=False)
    usage = result.usage
    assert usage is not None

    assert usage.duration_ms >= 0
    assert usage.started_at and usage.finished_at
    for call in usage.calls:
        assert call.duration_ms >= 0
        assert call.started_at and call.finished_at
    # Summed provider time is reported ALONGSIDE wall clock, not instead of it:
    # once calls overlap the two diverge, and the gap is the saving.
    assert usage.provider_seconds >= 0


def test_bytes_in_and_out_are_the_real_byte_counts():
    result = _run("bytes", count=2, bridges=False)
    usage = result.usage
    assert usage is not None

    photo_bytes = [len(PNG + bytes([i]) * (i + 1)) for i in range(2)]
    assert usage.to_dict()["input_bytes_to_provider"] == sum(photo_bytes)
    # Output bytes match what was actually stored for each step.
    per_step = {s.asset.filename: s.asset.size_bytes for s in result.steps}
    assert sum(c.output_bytes for c in usage.calls) == sum(per_step.values())


def test_objects_written_counts_every_single_write():
    """The number that predicts the Backblaze Class B transaction ceiling."""
    result = _run("objects", count=3)
    usage = result.usage
    assert usage is not None

    # 3 input photos + 4 clips + reel + manifest + provenance-embedded reel.
    assert usage.objects_written == 3 + 4 + 3
    assert usage.bytes_written > 0


def test_usage_never_invents_a_price():
    """No money. Not a currency symbol, not a rate, not an estimate."""
    blob = json.dumps(_run("nomoney", count=2, bridges=False).usage.to_dict()).lower()
    for forbidden in ("cost", "price", "usd", "eur", "$", "€", "dollar", "cent", "spend"):
        assert forbidden not in blob, f"invented a monetary figure: {forbidden!r}"


def test_usage_comes_back_from_the_job_poll_long_after_the_fact(monkeypatch):
    """The owner's actual need: read it per job, after the demo, not by
    grepping logs while it happens."""
    storage = FakeStorage(bucket="jobusage")
    monkeypatch.setattr(api, "_storage", storage)
    monkeypatch.setattr(api, "_pipeline", ReelPipeline(FakeMediaProvider(), storage))
    client = TestClient(api.app)

    import base64
    photos = [{"filename": "a.png", "content_base64": base64.b64encode(PNG).decode()}]
    submit = client.post("/reels/jobs", json={"name": "usage-job", "chapters": 1,
                                              "photos": photos})
    assert submit.status_code == 202
    job_id = submit.json()["job_id"]

    for _ in range(200):
        status = client.get(f"/reels/jobs/{job_id}").json()
        if status["status"] in ("done", "failed"):
            break
    assert status["status"] == "done", status

    usage = status["result"]["usage"]
    assert usage["provider_calls"] == 1
    assert usage["provider_calls_by_model"] == {"Kling-Image2Video-V2.1-Master": 1}
    assert usage["objects_written"] >= 4
    assert usage["duration_ms"] >= 0
    assert usage["max_concurrency"] >= 1
    # Per-call detail, not just a total.
    assert len(usage["calls"]) == 1
    assert usage["calls"][0]["model"] == "Kling-Image2Video-V2.1-Master"


def test_a_hand_built_result_carries_no_usage_rather_than_a_fabricated_one():
    """Absent beats invented. A result assembled without a run has nothing
    honest to report, so it reports nothing."""
    from cinemory.models import Asset, Modality, ReelResult

    body = api._reel_response(ReelResult(
        reel_name="hand", steps=[],
        reel_asset=Asset(modality=Modality.VIDEO, sha256="a" * 64, size_bytes=1),
    ))
    assert "usage" not in body


def test_the_operator_log_line_is_greppable():
    usage = _run("logline", count=2, bridges=False).usage
    line = usage.summary_line()
    assert "reel=logline" in line
    assert "calls=2" in line
    assert "objects=" in line and "concurrency=" in line


def test_a_backwards_clock_never_produces_a_negative_duration():
    usage = RunUsage(reel_name="odd")
    usage.finish(started_at="a", finished_at="b", elapsed_seconds=-3.0)
    assert usage.duration_ms == 0
