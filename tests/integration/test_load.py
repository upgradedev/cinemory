"""Integration load testing for Cinemory.

Verifies concurrent pipeline processing under load using a thread pool.
Measures latency and thread safety across multiple parallel generations.
"""
import base64
import concurrent.futures
import time

import pytest
from fastapi.testclient import TestClient

import cinemory.api as api
from cinemory import jobs
from cinemory.adapters import FakeMediaProvider, FakeStorage
from cinemory.models import Bridge
from cinemory.pipeline import ReelPipeline
from cinemory.synthetic import synth_reel_spec
from test_api_multitenancy import bearer_for  # noqa: F401 (pytest fixture, used by name)


def run_single_pipeline(worker_id):
    storage = FakeStorage(bucket=f"cinemory-load-bucket-{worker_id}")
    spec = synth_reel_spec(f"load-reel-{worker_id}", chapters=2, per_chapter=1)
    
    # Add a bridge
    spec.bridges.append(Bridge(spec.chapters[0].id, spec.chapters[1].id, "cross dissolve"))
    
    pipeline = ReelPipeline(FakeMediaProvider(), storage)
    
    start_time = time.time()
    result = pipeline.run(spec)
    duration = time.time() - start_time
    
    return duration, result

def test_concurrent_pipeline_generation_load():
    concurrency_level = 20
    durations = []
    
    # Execute 20 pipelines concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run_single_pipeline, i): i for i in range(concurrency_level)}
        
        for future in concurrent.futures.as_completed(futures):
            worker_id = futures[future]
            try:
                duration, result = future.result()
                durations.append(duration)
                # Verify result contains the generated steps
                assert len(result.steps) == 3 # 2 chapters + 1 bridge
            except Exception as e:
                pytest.fail(f"Worker {worker_id} failed with exception: {e}")
                
    avg_duration = sum(durations) / len(durations)
    print(f"\nAverage generation duration under load: {avg_duration:.3f}s")
    
    assert len(durations) == concurrency_level
    assert avg_duration < 2.0 # Average pipeline compilation must be fast


# ── Async job endpoints + multitenancy under concurrent load ──
# The load test above only drives the bare pipeline directly. These two tests
# drive the real FastAPI app (like every other tests/integration/test_api_*.py
# file) against the endpoints added this week: POST /reels/jobs (async submit
# + poll, see test_api_jobs.py) and optional per-user multitenancy (see
# test_api_multitenancy.py). Both are fully offline (FakeStorage,
# FakeMediaProvider, FakeStitcher), so they stay fast and deterministic.
#
# Each concurrent submission below uses its own fresh TestClient(api.app)
# instance rather than one client shared across threads, so the concurrency
# genuinely under test is the ASGI app and the shared storage object, not the
# test harness itself. Sequential work after the thread pool has joined (the
# poll loop, the /me/library isolation checks) reuses one module-level
# client, exactly like every other integration test file. The shared
# FakeStorage is safe to mutate from many threads at once because every
# concurrent writer here touches a distinct key (see cinemory.api._job_storage
# docstring): plain dict/list mutation under the GIL, no read-modify-write
# race between them.

client = TestClient(api.app)


def _submit_load_job(worker_id: int) -> tuple[int, str]:
    photos = [{
        "filename": "p.png",
        "content_base64": base64.b64encode(f"load-job-pixels-{worker_id}".encode()).decode(),
    }]
    r = TestClient(api.app).post(
        "/reels/jobs", json={"name": f"load-job-{worker_id}", "photos": photos},
    )
    if r.status_code != 202:
        raise AssertionError(f"worker {worker_id} submission returned {r.status_code}: {r.text}")
    return worker_id, r.json()["job_id"]


def _poll_load_job_until_terminal(job_id: str, *, timeout: float = 5.0) -> dict:
    """Bounded poll for one job, on the shared sequential client. Offline
    generation is near-instant; this timeout is a generous ceiling, not an
    expected wait (mirrors the poll helper in test_api_jobs.py)."""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        r = client.get(f"/reels/jobs/{job_id}")
        if r.status_code == 200:
            body = r.json()
            if body.get("status") in jobs.TERMINAL_STATUSES:
                return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach a terminal status within {timeout}s: {body}")


def test_concurrent_async_job_submission_load():
    """Many concurrent POST /reels/jobs submissions, each polled to done.

    This is the risky part test_concurrent_pipeline_generation_load never
    touches: create_reel_job (see cinemory.api) hands out a fresh job id and
    spins up a real background thread per submission - under real
    concurrency that means many such threads racing to write their own
    jobs/<id>/status.json into the same shared storage at once. Every
    submission must return 202 (never a 500 from a race in job-id generation
    or status creation), every handed-out job_id must be unique, and every
    job must independently reach done.
    """
    concurrency_level = 20
    job_ids: dict[int, str] = {}

    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_submit_load_job, i): i for i in range(concurrency_level)}
        for future in concurrent.futures.as_completed(futures):
            worker_id = futures[future]
            try:
                wid, job_id = future.result()
                job_ids[wid] = job_id
            except Exception as e:
                pytest.fail(f"worker {worker_id} submission failed: {e}")
    submit_duration = time.time() - start_time
    print(f"\n{concurrency_level} concurrent job submissions took {submit_duration:.3f}s")

    assert len(job_ids) == concurrency_level
    assert len(set(job_ids.values())) == concurrency_level, "every job_id must be unique"

    for worker_id, job_id in job_ids.items():
        status = _poll_load_job_until_terminal(job_id)
        assert status["status"] == "done", (
            f"job {job_id} (worker {worker_id}) never completed: {status}"
        )
        assert status["result"]["reel_name"] == f"load-job-{worker_id}"


def _create_load_reel(tenant_headers: dict | None, name: str) -> int:
    r = TestClient(api.app).post(
        "/reels", json={"name": name, "chapters": 1, "per_chapter": 1},
        headers=tenant_headers or {},
    )
    return r.status_code


def test_concurrent_multitenant_isolation_under_load(bearer_for):
    """Several tenants (plus guest) creating reels at the same time never
    bleed into each other's GET /me/library - isolation must hold under real
    concurrency, not merely when requests happen to be sequential (compare
    test_api_multitenancy.py's sequential proof of the same property).
    Tokens are minted with that file's own bearer_for fixture (imported, not
    reinvented - see its docstring for the offline RSA-keypair mechanism):
    one keypair for the whole test, a distinct signed token per tenant uid.
    """
    tenants = ["load-mt-a", "load-mt-b", "load-mt-c", "load-mt-d"]
    reels_per_tenant = 4
    guest_reels = 4
    headers_by_tenant = {t: bearer_for(t) for t in tenants}

    jobs_to_run: list[tuple[str | None, str]] = [
        (t, f"load-mt-reel-{t}-{i}") for t in tenants for i in range(reels_per_tenant)
    ] + [(None, f"load-mt-reel-guest-{i}") for i in range(guest_reels)]

    def _worker(job: tuple[str | None, str]) -> tuple[str | None, str, int]:
        tenant, name = job
        status = _create_load_reel(headers_by_tenant[tenant] if tenant else None, name)
        return tenant, name, status

    results: list[tuple[str | None, str, int]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_worker, job) for job in jobs_to_run]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                pytest.fail(f"concurrent reel creation failed: {e}")

    assert len(results) == len(jobs_to_run)
    for tenant, name, status in results:
        assert status == 200, f"{tenant or 'guest'}'s reel {name!r} creation returned {status}"

    # Strict isolation, checked after the concurrent storm settles: every
    # tenant's own reels are all present, and none of another tenant's or a
    # guest's reels ever appear in it (subset + negative checks against the
    # shared, process-wide storage - the same pattern test_api_multitenancy.py
    # itself uses, not an exact-equality check on global state).
    for t in tenants:
        lib = client.get("/me/library", headers=headers_by_tenant[t]).json()
        names = {r["reel_name"] for r in lib["reels"]}
        expected = {f"load-mt-reel-{t}-{i}" for i in range(reels_per_tenant)}
        assert expected <= names, f"tenant {t} is missing some of its own reels: {expected - names}"

        other_tenants_reels = {
            f"load-mt-reel-{other}-{i}"
            for other in tenants if other != t
            for i in range(reels_per_tenant)
        }
        assert not (names & other_tenants_reels), (
            f"tenant {t} can see another tenant's reel: {names & other_tenants_reels}"
        )
        assert not any(n.startswith("load-mt-reel-guest-") for n in names), (
            "tenant library must never contain a guest reel"
        )

    # Guest reels are fetchable unauthenticated, and invisible to every tenant.
    for i in range(guest_reels):
        name = f"load-mt-reel-guest-{i}"
        assert client.get(f"/reels/{name}").status_code == 200
        for t in tenants:
            assert client.get(f"/reels/{name}", headers=headers_by_tenant[t]).status_code == 404
