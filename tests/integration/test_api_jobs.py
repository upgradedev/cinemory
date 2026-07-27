"""Integration tests for async reel generation (submit + poll) — the M2 fix.

``POST /reels/jobs`` accepts the identical body as ``POST /reels/upload`` but
returns ``202`` + a job id immediately instead of blocking for the full
generation; ``GET /reels/jobs/{job_id}`` polls the stored status back. Driven
through the real FastAPI app, offline (FakeStorage + FakeMediaProvider +
FakeStitcher), so "background" generation is effectively instant — the tests
still poll with a short bounded timeout rather than assume one check
suffices, since the work genuinely runs on a separate thread.

The existing synchronous endpoints (``tests/integration/test_api.py`` and
friends) are untouched by this file and by the refactor that backs it — see
``src/cinemory/api.py``'s ``_build_spec``/``_decode_photos``/``_run_reel``.
"""
from __future__ import annotations

import base64
import json
import time

from fastapi.testclient import TestClient

import cinemory.api as api
from cinemory import jobs
from cinemory.adapters import FakeMediaProvider
from cinemory.pipeline import ReelPipeline

client = TestClient(api.app)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _poll_until_terminal(c: TestClient, job_id: str, *, timeout: float = 5.0) -> dict:
    """Poll GET /reels/jobs/{job_id} until it reaches a terminal status.

    Offline generation is effectively instant (no real I/O), so 5s is a very
    generous ceiling — this just avoids a hard assumption that the background
    thread has already finished by the time the first poll lands.
    """
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        r = c.get(f"/reels/jobs/{job_id}")
        assert r.status_code == 200
        body = r.json()
        if body.get("status") in jobs.TERMINAL_STATUSES:
            return body
        time.sleep(0.02)
    raise AssertionError(
        f"job {job_id} did not reach a terminal status within {timeout}s: {body}"
    )


def test_submit_returns_202_with_job_id_and_queued_status():
    photos = [{"filename": f"p{i}.png", "content_base64": _b64(f"pixels-{i}".encode())}
              for i in range(3)]
    r = client.post("/reels/jobs", json={"name": "asyncjob-submit", "occasion": "wedding",
                                         "chapters": 2, "photos": photos})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert isinstance(body["job_id"], str) and body["job_id"]


def test_poll_reaches_done_with_real_provenance_result():
    photos = [{"filename": f"p{i}.png", "content_base64": _b64(f"pixels-{i}".encode())}
              for i in range(4)]
    r = client.post("/reels/jobs", json={"name": "asyncjob-done", "occasion": "anniversary",
                                         "chapters": 2, "photos": photos})
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    status = _poll_until_terminal(client, job_id)
    assert status["status"] == "done"
    assert status["job_id"] == job_id
    assert status["created_at"] and status["updated_at"]

    result = status["result"]
    assert result["reel_name"] == "asyncjob-done"
    assert result["occasion"] == "anniversary"
    assert len(result["reel_sha256"]) == 64
    assert result["manifest_hash"]
    assert result["steps"] == 4  # 4 photos -> 4 clips, no bridges by default
    assert result["provider_degraded"] is False
    assert "playback_url" in result and "manifest_uri" in result

    # The job's generation really landed in storage — fetchable the normal way.
    manifest = client.get("/reels/asyncjob-done").json()
    assert manifest["reel_name"] == "asyncjob-done"


def test_poll_with_bridges_matches_sync_step_count():
    photos = [{"filename": f"p{i}.png", "content_base64": _b64(f"x{i}".encode())}
              for i in range(4)]
    r = client.post("/reels/jobs", json={"name": "asyncjob-bridges", "chapters": 2,
                                         "bridges": True, "photos": photos})
    assert r.status_code == 202
    status = _poll_until_terminal(client, r.json()["job_id"])
    assert status["status"] == "done"
    assert status["result"]["steps"] == 5  # 4 clips + 1 bridge, same as the sync path


def test_submit_no_photos_is_400_synchronously():
    """Ingest validation happens BEFORE a job is created — same 400 as the
    sync endpoint, no job id handed out for a request that will never run."""
    r = client.post("/reels/jobs", json={"name": "asyncjob-empty", "photos": []})
    assert r.status_code == 400


def test_submit_bad_base64_is_400_synchronously():
    r = client.post("/reels/jobs", json={
        "name": "asyncjob-badb64",
        "photos": [{"filename": "p.png", "content_base64": "not!base64!!"}]})
    assert r.status_code == 400


def test_unknown_job_id_is_404():
    r = client.get("/reels/jobs/does-not-exist")
    assert r.status_code == 404


def test_corrupt_stored_status_degrades_to_404_not_500():
    """A status object that exists but doesn't parse degrades the same way an
    unknown job id does (see cinemory.jobs.read) — never a 500."""
    api._storage.put("jobs/corrupt-job/status.json", b"not valid json")
    r = client.get("/reels/jobs/corrupt-job")
    assert r.status_code == 404


def test_job_forced_failure_marks_status_failed_not_500(monkeypatch):
    """A generation failure surfaces ONLY through the polled status — never as
    an HTTP error anywhere in the submit/poll flow. Mirrors the sync path's
    ``test_offline_provider_failure_is_a_real_500`` fixture (a FakeMediaProvider
    subclass that raises), except here the offline failure has nowhere to
    "surface" as a request 500, because the generation never happens on a
    request thread at all."""

    class _BrokenFake(FakeMediaProvider):
        def generate(self, **_kwargs) -> bytes:
            raise RuntimeError("offline provider bug (forced for this test)")

    monkeypatch.setattr(
        api, "_job_pipeline", lambda storage: ReelPipeline(_BrokenFake(), storage)
    )

    photos = [{"filename": "p.png", "content_base64": _b64(b"px-bytes")}]
    r = client.post("/reels/jobs", json={"name": "asyncjob-forced-fail", "photos": photos})
    # The submit itself never sees the failure — it happens later, in the
    # background thread.
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    status = _poll_until_terminal(client, job_id)
    assert status["status"] == "failed"
    assert status["error"] == "RuntimeError"
    assert "result" not in status
    # Class name only — the raw exception text never reaches the response.
    assert "forced for this test" not in json.dumps(status)
