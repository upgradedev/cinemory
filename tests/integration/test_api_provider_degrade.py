"""Per-request provider degrade: a live-provider failure must never 500.

``test_api_live_degrade.py`` covers the *boot-time* contract (live mode with no
credentials wires the offline fakes). This file covers the *runtime* contract:
the live provider is wired and healthy at boot but a request fails mid-flight
(e.g. an upstream 400/timeout). The API must regenerate THAT request with the
offline provider against the same storage and say so honestly — a degraded
``200`` whose body carries ``provider_degraded: true`` plus the provider that
actually generated, with the sealed manifest recording the same provider on
every step. Nothing lies; nothing 500s for a remote-backend reason.
"""
from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

import cinemory.api as api
from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.pipeline import ReelPipeline


class _ExplodingLiveProvider:
    """Stands in for the live Genblaze adapter failing mid-request."""

    name = "genblaze"

    def generate(self, **_kwargs) -> bytes:
        raise RuntimeError("GMICloud submit failed (400): invalid payload parameters")


class _RealVideoOnlyStitcher:
    """Stands in for the live ``FfmpegStitcher``: real video tooling cannot
    decode the offline provider's deterministic clip bytes, so the degrade
    path must NOT inherit the live pipeline's stitcher."""

    name = "ffmpeg-stitcher"

    def stitch(self, clips: list[bytes]) -> bytes:
        raise RuntimeError("cannot decode non-video clip bytes")


@pytest.fixture
def degrade_client(monkeypatch):
    """The API wired like the live box: a provider that fails on every generate
    call AND a stitcher that only accepts real video (the harshest degrade
    configuration)."""
    storage = FakeStorage(bucket="degrade-test")
    monkeypatch.setattr(api, "_storage", storage)
    monkeypatch.setattr(
        api,
        "_pipeline",
        ReelPipeline(_ExplodingLiveProvider(), storage, stitcher=_RealVideoOnlyStitcher()),
    )
    return TestClient(api.app)


def test_live_provider_failure_degrades_to_200_with_honest_flags(degrade_client):
    r = degrade_client.post("/reels", json={"name": "boom", "chapters": 2, "per_chapter": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is True
    assert body["provider"] == "fake-genblaze"
    assert body["degrade_reason"] == "RuntimeError"
    # The degraded reel is still a real sealed reel.
    assert len(body["reel_sha256"]) == 64
    assert body["manifest_hash"]
    assert body["steps"] == 2
    # The sealed manifest records the provider that ACTUALLY generated.
    manifest = degrade_client.get("/reels/boom").json()
    assert manifest["steps"]
    assert all(s["provider"] == "fake-genblaze" for s in manifest["steps"])


def test_upload_path_degrades_too(degrade_client):
    photos = [{"filename": "p.png", "content_base64": base64.b64encode(b"px-bytes").decode()}]
    r = degrade_client.post("/reels/upload", json={"name": "boom-up", "photos": photos})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is True
    assert body["provider"] == "fake-genblaze"
    assert len(body["reel_sha256"]) == 64


def test_ingest_400_is_not_swallowed_by_degrade(degrade_client):
    """Client errors stay client errors — degrade only covers provider failures."""
    r = degrade_client.post("/reels/upload", json={"name": "empty", "photos": []})
    assert r.status_code == 400


def test_healthy_pipeline_reports_not_degraded():
    client = TestClient(api.app)  # module default: offline fakes
    r = client.post("/reels", json={"name": "ok-flag", "chapters": 1, "per_chapter": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["provider_degraded"] is False
    assert body["provider"] == "fake-genblaze"


def test_offline_provider_failure_is_a_real_500(monkeypatch):
    """Degrade masks only LIVE provider failures; the offline fake failing is a
    genuine bug and must surface, not be retried into a lie."""

    class _BrokenFake(FakeMediaProvider):
        def generate(self, **_kwargs) -> bytes:
            raise RuntimeError("offline provider bug")

    storage = FakeStorage(bucket="bug")
    monkeypatch.setattr(api, "_storage", storage)
    monkeypatch.setattr(api, "_pipeline", ReelPipeline(_BrokenFake(), storage))
    client = TestClient(api.app, raise_server_exceptions=False)
    r = client.post("/reels", json={"name": "bug", "chapters": 1, "per_chapter": 1})
    assert r.status_code == 500


# ── Why it degraded, in a form a browser may see ──────────────────────────────
# The classification added after the live account ran out of credit: the API
# already degraded honestly, but the response said nothing about the CAUSE, so
# a visitor saw only "taking longer than expected" and the owner had to read
# Cloud Logging to find out that the bill was the problem.


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        # The real incident, verbatim from the log.
        ("GMICloud submit failed (402): Insufficient credits", "credit"),
        ("payment required", "credit"),
        ("monthly quota exhausted", "credit"),
        ("429 Too Many Requests", "busy"),
        ("upstream rate limit hit", "busy"),
        ("read timeout after 600s", "timeout"),
        ("context deadline exceeded", "timeout"),
        ("503 Service Unavailable", "unavailable"),
        ("connection refused", "unavailable"),
        ("401 unauthorized", "refused"),
        ("submit failed (400): invalid payload parameters", "refused"),
        # Nothing recognisable is not an error: the UI renders the honest
        # general sentence for it.
        ("the moon was in the wrong phase", "unknown"),
        ("", "unknown"),
    ],
)
def test_degrade_kind_classifies_the_failures_that_actually_happen(message, expected):
    assert api._degrade_kind(RuntimeError(message)) == expected


def test_degrade_kind_reads_the_exception_class_too():
    """Some clients raise a typed error with an empty message."""

    class ConnectionError_(Exception):
        pass

    ConnectionError_.__name__ = "ConnectionError"
    assert api._degrade_kind(ConnectionError_()) == "unavailable"


def test_degrade_kind_never_raises_on_a_hostile_exception():
    class Nasty(Exception):
        def __str__(self) -> str:  # pragma: no cover - exercised via the call below
            return "\x00\udcff weird"

    assert api._degrade_kind(Nasty()) in {
        "credit", "busy", "timeout", "unavailable", "refused", "unknown",
    }


def test_degraded_response_carries_the_category_but_never_the_message(degrade_client):
    """The category crosses the wire; the upstream text never does.

    ``_ExplodingLiveProvider`` raises a message containing the provider's own
    name and its raw upstream detail. The response must carry the classified
    category and the exception CLASS name only, with none of that text
    anywhere in the body.
    """
    r = degrade_client.post("/reels", json={"name": "why", "chapters": 2, "per_chapter": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["degrade_kind"] == "refused"  # "(400): invalid payload parameters"
    assert body["degrade_reason"] == "RuntimeError"

    raw = r.text.lower()
    for leak in ("gmicloud", "invalid payload", "submit failed", "traceback"):
        assert leak not in raw, f"leaked {leak!r} into the API response"


def test_a_healthy_run_carries_no_category_at_all():
    """Nothing to explain, nothing said. The UI keys its whole explanation off
    ``provider_degraded``, so a clean run must not carry a stray category."""
    storage = FakeStorage(bucket="ok-test")
    pipeline = ReelPipeline(FakeMediaProvider(), storage)
    body = api._run_reel(
        api._build_spec(
            "clean",
            [("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)],
            occasion="anniversary",
            chapters=1,
            bridges=False,
        ),
        pipeline,
    )
    assert body["provider_degraded"] is False
    assert "degrade_kind" not in body
    assert "degrade_reason" not in body
