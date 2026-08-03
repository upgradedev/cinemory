"""Cinemory HTTP API (FastAPI).

Routes:
  GET  /health           liveness + active mode
  GET  /occasions        list selectable occasion presets (themes)
  POST /reels            generate a reel from a synthetic spec, return provenance
  POST /reels/upload     generate a reel from real uploaded photos (base64 JSON)
  POST /reels/upload-multipart
                         generate a reel from real uploaded photos (multipart)
  POST /reels/jobs       submit a reel generation as a background job (202 +
                         job_id) — does not block for the full generation
  GET  /reels/jobs/{job_id}
                         poll a submitted job's status (queued/running/done/failed)
  GET  /reels/{name}     fetch the stored provenance manifest for a reel
  GET  /reels/{name}/video
                         play back the stored reel (302 to a fresh presigned
                         URL in live mode; streamed bytes offline)
  GET  /me/library       an authed tenant's own reels (401 for guest)
  DELETE /me/data        delete every object under an authed tenant's own
                         prefix (401 for guest)

The API is storage/provider agnostic (see ``config``): offline by default so it
boots and serves with no credentials. In ``live`` mode it uses the real
Genblaze/B2 backends only when their credentials are present, otherwise it
transparently degrades to the offline path — so reel generation never 500s.
The same contract holds per request: when the live provider fails mid-request,
the reel is regenerated with the offline provider (storage unchanged) and the
response says so honestly (``provider_degraded`` + the actual ``provider``,
which the sealed manifest also records per step).

Async submit + poll (``POST /reels/jobs`` / ``GET /reels/jobs/{job_id}``): the
synchronous ``POST /reels*`` routes above can run for minutes (a real render
averages ~242s — see ``deploy/CLOUDRUN.md``), longer than the Firebase Hosting
proxy cap (~60s), so a caller that cannot hold one request open that long
submits a job and polls it instead. The async routes run the exact same ingest
validation and pipeline as the synchronous ones (see ``_run_job`` below and the
``cinemory.jobs`` module for the job-store design and its honest limitation —
the worker runs in-process on the instance that accepted the submit).

Optional per-user multitenancy (see ``cinemory.auth`` and ``get_tenant``
below): every reel route accepts an optional ``Authorization: Bearer
<Firebase ID token>`` header. Absent — or ``FIREBASE_PROJECT_ID`` unset on
this deployment — every request is GUEST, the exact behaviour this API has
always had. A verified token scopes that request's storage/pipeline to a
``tenants/<uid>/`` prefix (``_tenant_storage``/``_TenantScopedStorage``), so
a signed-in caller's uploads and reels are isolated from every other tenant
and from guest data — by construction (a tenant's index scan can only ever
see rows under its own prefix), not by a check that could be forgotten. See
``GET /me/library`` and ``DELETE /me/data`` for self-service listing/erasure.
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from . import auth, config, failures, jobs
from .adapters import FakeMediaProvider, FakeStorage
from .ingest import IngestError, build_spec_from_photos
from .models import ReelResult, ReelSpec
from .occasions import list_occasions
from .pipeline import ReelPipeline
from .ports import StorageBackend
from .provenance import verify_all
from .stitch import FakeStitcher
from .synthetic import synth_reel_spec

_log = logging.getLogger("cinemory.api")

app = FastAPI(title="Cinemory API", version="0.1.0")

# Storage is process-lived so a generated reel can be fetched back by name.
_storage = config.build_storage()
_pipeline = ReelPipeline(config.build_provider(), _storage, stitcher=config.build_stitcher())


class ReelRequest(BaseModel):
    name: str = "demo-reel"
    chapters: int = 3
    per_chapter: int = 2
    occasion: str = "anniversary"


class UploadedPhoto(BaseModel):
    filename: str = "photo.png"
    content_base64: str


class UploadReelRequest(BaseModel):
    name: str = "uploaded-reel"
    occasion: str = "anniversary"
    chapters: int = 3
    bridges: bool = False
    photos: list[UploadedPhoto] = Field(default_factory=list)


def _reel_response(result: ReelResult) -> dict:
    return {
        "reel_name": result.reel_name,
        "occasion": result.occasion,
        # Canonical storage URL (provenance display). The bucket is private, so
        # this is NOT directly fetchable by a browser — playback goes through
        # the stable, api-relative ``playback_url`` below, which redirects to a
        # fresh presigned URL (live) or streams the bytes (offline).
        "reel_url": result.reel_asset.url,
        "playback_url": f"/reels/{quote(result.reel_name, safe='')}/video",
        "reel_sha256": result.reel_asset.sha256,
        "manifest_uri": result.manifest_uri,
        "manifest_hash": result.manifest_hash,
        "steps": len(result.steps),
        # What this run burned: provider calls per model, wall clock per call
        # and for the run, bytes to and from the provider, objects written to
        # storage (see cinemory.usage). Carried on the response, so it lands in
        # the stored job status and comes back from GET /reels/jobs/{job_id}
        # for any run, at any time afterwards. Absent only for a result built
        # by hand (tests); never fabricated.
        **({"usage": result.usage.to_dict()} if result.usage is not None else {}),
    }


def _degrade_kind(exc: BaseException) -> str:
    """Classify a live-provider failure into ONE coarse, visitor-safe category.

    The category is the ONLY thing about the failure that crosses the wire.
    Everything the exception actually said, which can embed upstream URLs,
    request identifiers, account details, or a raw provider response body,
    stays in this process's log, where an operator can find it and a browser
    cannot. That split is the whole point: before it existed, a visitor whose
    reel silently fell back learned nothing, and the owner had to read Cloud
    Logging to discover the account had run out of credit.

    The rules themselves live in :mod:`cinemory.failures`, shared with the
    pipeline, which asks the same classifier a different question: whether a
    failure is worth retrying. One vocabulary, two readers.
    """
    return failures.classify(exc)


def _run_reel(spec: ReelSpec, pipeline: ReelPipeline | None = None) -> dict:
    """Run the pipeline; degrade THIS request honestly if the live provider fails.

    The core action must never 500 because a remote generation backend
    misbehaved: on a live-provider failure the same spec is regenerated with
    the offline provider against the *same* storage (real B2 in live mode).
    Nothing lies about it — the response carries ``provider_degraded: true``
    plus the provider that actually generated, and the sealed manifest records
    that provider on every step. A failure of the offline provider itself is a
    genuine bug and propagates (500) rather than being masked.

    ``pipeline`` defaults to the module-level synchronous pipeline. The async
    job worker (``_run_job``) passes its own isolated pipeline instead (see
    ``_job_pipeline``), so a background thread never shares mutable adapter
    state with a request thread — the honest-degrade fallback below then also
    writes to THAT pipeline's storage, not necessarily the module-level one.
    """
    pipeline = pipeline or _pipeline
    try:
        body = _reel_response(pipeline.run(spec))
        body["provider"] = pipeline.provider.name
        body["provider_degraded"] = False
        return body
    except HTTPException:
        raise
    except Exception as exc:
        if isinstance(pipeline.provider, FakeMediaProvider):
            raise
        kind = _degrade_kind(exc)
        # The operator's copy of the truth: full traceback, full exception text,
        # plus the category the browser was told — so a report of "it said the
        # credit ran out" is greppable straight back to the real upstream
        # failure that produced it.
        _log.exception(
            "live media provider %r failed for reel %r (degrade_kind=%s); regenerating "
            "this request with the offline provider (storage unchanged)",
            pipeline.provider.name,
            spec.name,
            kind,
        )
        # The offline provider's deterministic clips are not decodable video,
        # so the regeneration pairs it with the offline stitcher (a real
        # ffmpeg stitcher would fail on them) — the exact offline generation
        # path, persisted to whatever storage the deployment actually uses.
        fallback = ReelPipeline(FakeMediaProvider(), pipeline.storage, stitcher=FakeStitcher())
        body = _reel_response(fallback.run(spec))
        body["provider"] = fallback.provider.name
        body["provider_degraded"] = True
        # Class name only — exception text may embed URLs/identifiers that do
        # not belong in an API response; the full traceback is in the log.
        body["degrade_reason"] = type(exc).__name__
        # The plain-language category (never the message itself). The UI maps
        # it to a sentence; nothing here is provider-identifying.
        body["degrade_kind"] = kind
        return body


def _build_spec(
    name: str, photos: list[tuple[str, bytes]], *, occasion: str, chapters: int, bridges: bool
) -> ReelSpec:
    """Ingest validation shared by every upload path — sync AND async."""
    try:
        return build_spec_from_photos(
            name, photos, occasion=occasion, chapters=chapters, bridges=bridges
        )
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc


def _generate_from_photos(
    name: str, photos: list[tuple[str, bytes]], *, occasion: str, chapters: int, bridges: bool,
    pipeline: ReelPipeline,
) -> dict:
    """Shared ingest path for both SYNCHRONOUS upload endpoints (base64 + multipart).

    ``pipeline`` is always supplied by the caller now (see ``_tenant_pipeline``
    below) — every route passes ``_tenant_pipeline(tenant)``, which for GUEST
    (``tenant is None``) resolves to the exact module-level ``_pipeline``, so
    this is byte-identical to the pre-multitenancy behaviour for guest.
    """
    spec = _build_spec(name, photos, occasion=occasion, chapters=chapters, bridges=bridges)
    return _run_reel(spec, pipeline)


# ── Optional per-user multitenancy (see cinemory.auth) ─────────────────────────
# A signed-in caller's uploads/reels are isolated to their OWN tenant prefix —
# BY CONSTRUCTION, not by a check that could be forgotten: every lookup in this
# module resolves a reel through a storage object's ``index``, and
# ``_TenantScopedStorage.index`` physically cannot contain a row outside its
# own prefix (see its docstring). Guest (no/absent header, or multitenancy off
# entirely — see ``get_tenant``) always resolves to the SAME objects this API
# used before this section existed (``_storage`` / ``_pipeline`` directly, no
# wrapper), so guest behaviour is byte-identical.


def get_tenant(authorization: Annotated[str | None, Header()] = None) -> str | None:
    """FastAPI dependency: the caller's verified tenant id, or ``None`` for guest.

    - ``FIREBASE_PROJECT_ID`` unset -> multitenancy is OFF for this deployment:
      ALWAYS returns ``None``, even when ``authorization`` is present — this is
      what keeps a deploy with no such env var configured (the current
      production default) behaving exactly as it did before this dependency
      existed. The header is not even inspected in that case.
    - No/empty ``authorization`` -> ``None`` (GUEST; not an error).
    - A well-formed, valid ``Bearer <token>`` -> the token's verified ``uid``.
    - A PRESENT but invalid/expired/malformed credential -> ``HTTPException
      (401)``. A bad credential must never silently downgrade to guest (see
      ``auth.uid_from_authorization``'s own contract).

    The tenant id comes ONLY from here — the verified token's ``sub`` claim.
    Nothing in this module ever reads a tenant from a query param, request
    body field, cookie, or any header other than ``Authorization``, so it is
    structurally impossible for a caller to set their own tenant.
    """
    project_id = os.environ.get(auth.PROJECT_ID_ENV_VAR)
    if not project_id:
        return None
    try:
        return auth.uid_from_authorization(authorization, project_id=project_id)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc


def _tenant_prefix(uid: str) -> str:
    """The storage-key prefix a verified tenant's data lives under."""
    from .keys import safe_component

    return f"tenants/{safe_component(uid)}/"


class _TenantScopedStorage:
    """A tenant-prefixing view over a base :class:`~cinemory.ports.StorageBackend`
    — the isolation core of multitenancy.

    Every key a caller passes to ``put``/``get``/``exists``/``get_url``/
    ``delete`` is a TENANT-RELATIVE key; ``prefix`` is prepended before it ever
    reaches the base backend. ``index`` does the reverse for reads: it returns
    ONLY the base backend's rows whose key starts with ``prefix``, with the
    prefix stripped back off — so the existing ``<name>/<kind>/<sha2>/<sha256>/
    <file>`` matching in ``_reel_index_match``/``_artifact_fetcher`` (and
    ``cinemory.jobs``' ``jobs/<id>/status.json`` keys) works completely
    unchanged against a tenant-scoped view, and a tenant's index scan is
    PHYSICALLY UNABLE to enumerate a row outside its own prefix — a
    cross-tenant (or guest) lookup 404s because the row is never in the list to
    begin with, not because a comparison happened to reject it.

    There is no method on this class parameterised by anything a caller
    controls: ``prefix`` is fixed at construction from a VERIFIED uid (see
    ``_tenant_storage``), so nothing reachable through this object can ever
    address a key outside it.

    Mirrors the prepend-on-every-call shape of
    ``cinemory.adapters.genblaze_provider.PrefixedS3StorageBackend``, but
    composes over any ``StorageBackend``-shaped object instead of subclassing
    a specific SDK base class.

    ``get_url``/``delete`` are exposed only when the base backend has them —
    mirrors this codebase's existing ``getattr(storage, "get_url", None)``
    capability-probing pattern, so a FakeStorage-backed tenant (no
    ``get_url``) falls through to the byte-streaming playback path exactly
    like guest FakeStorage does, instead of a broken redirect.
    """

    def __init__(self, base: StorageBackend, prefix: str) -> None:
        self._base = base
        self._prefix = prefix

        base_get_url = getattr(base, "get_url", None)
        if callable(base_get_url):
            def get_url(key: str, *, expires_in: int = 3600) -> str:
                return base_get_url(f"{prefix}{key}", expires_in=expires_in)
            self.get_url = get_url

        base_delete = getattr(base, "delete", None)
        if callable(base_delete):
            def delete(key: str) -> None:
                return base_delete(f"{prefix}{key}")
            self.delete = delete

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        return self._base.put(f"{self._prefix}{key}", data, content_type=content_type)

    def get(self, key: str) -> bytes:
        return self._base.get(f"{self._prefix}{key}")

    def exists(self, key: str) -> bool:
        return self._base.exists(f"{self._prefix}{key}")

    @property
    def index(self) -> list[dict]:
        if not hasattr(self._base, "index"):  # pragma: no cover - defensive
            raise AttributeError("index")
        return [
            {**row, "key": row["key"][len(self._prefix):]}
            for row in self._base.index
            if row.get("key", "").startswith(self._prefix)
        ]

    def reload_index(self) -> list[dict]:
        """Always safe to call, regardless of base capability — mirrors this
        codebase's ``if callable(reload_index): reload_index()`` opportunistic
        pattern; a base without one is just a no-op here."""
        reload = getattr(self._base, "reload_index", None)
        if callable(reload):
            reload()
        return self.index


def _tenant_storage(uid: str | None) -> StorageBackend:
    """The request-time storage for ``uid`` — tenant-scoped, or GUEST.

    GUEST (``uid is None``) returns the EXACT module-level ``_storage``
    object — no wrapper — so every existing guest code path (including tests
    that monkeypatch ``api._storage`` directly) is byte-identical to before
    multitenancy existed. An authed uid gets a fresh ``_TenantScopedStorage``
    over that SAME shared storage.
    """
    if uid is None:
        return _storage
    return _TenantScopedStorage(_storage, _tenant_prefix(uid))


def _build_info() -> dict:
    """Which commit the running image was built from, and when.

    Baked into the image at build time (see ``Dockerfile`` and
    ``deploy/cloudbuild.yaml``), so anyone can check that a deployment really
    is the commit they are reading on GitHub, without access to the project:

        curl -s <url>/health | jq -r .build.commit

    Both values are ``None`` when the app was not built through that path (a
    local run, or CI), which is the honest answer rather than a fabricated one.
    A commit hash is public information, so exposing it leaks nothing.
    """
    return {
        "commit": os.environ.get("CINEMORY_BUILD_SHA") or None,
        "built_at": os.environ.get("CINEMORY_BUILD_TIME") or None,
    }


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "cinemory-api",
        "mode": config.mode(),
        # Effective backends after credential-aware resolution, so a live deploy
        # running without creds is visibly degraded (not silently mislabelled).
        "provider": _pipeline.provider.name,
        "storage": type(_storage).__name__,
        "build": _build_info(),
    }


@app.get("/occasions")
def occasions() -> dict:
    return {"occasions": list_occasions()}


@app.post("/reels")
def create_reel(
    req: ReelRequest, tenant: Annotated[str | None, Depends(get_tenant)]
) -> dict:
    spec = synth_reel_spec(req.name, chapters=req.chapters, per_chapter=req.per_chapter,
                           occasion=req.occasion)
    return _run_reel(spec, _tenant_pipeline(tenant))


def _decode_photos(photos: list[UploadedPhoto]) -> list[tuple[str, bytes]]:
    """Decode base64 photo payloads — shared by the base64 upload path, sync
    (``/reels/upload``) AND async (``/reels/jobs``): same validation, same 400
    message, same order."""
    decoded: list[tuple[str, bytes]] = []
    for i, p in enumerate(photos):
        try:
            data = base64.b64decode(p.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(400, f"photo {i} is not valid base64") from exc
        decoded.append((p.filename or f"photo{i}.png", data))
    return decoded


@app.post("/reels/upload")
def upload_reel(
    req: UploadReelRequest, tenant: Annotated[str | None, Depends(get_tenant)]
) -> dict:
    """Generate a reel from real photo bytes sent as base64 JSON.

    This is the dependency-free ingest path the mobile/web client uses to send
    actual pixels; the decoded photos flow through the same storage + pipeline as
    the synthetic demo, sealing real SHA-256 provenance.
    """
    photos = _decode_photos(req.photos)
    return _generate_from_photos(
        req.name, photos, occasion=req.occasion, chapters=req.chapters, bridges=req.bridges,
        pipeline=_tenant_pipeline(tenant),
    )


@app.post("/reels/upload-multipart")
async def upload_reel_multipart(
    files: Annotated[list[UploadFile], File()],
    tenant: Annotated[str | None, Depends(get_tenant)],
    name: Annotated[str, Form()] = "uploaded-reel",
    occasion: Annotated[str, Form()] = "anniversary",
    chapters: Annotated[int, Form()] = 3,
    bridges: Annotated[bool, Form()] = False,
) -> dict:
    """Generate a reel from real photo bytes sent as multipart/form-data.

    The efficient path for a native mobile upload (Flutter ``MultipartFile``):
    raw bytes, no base64 inflation. Requires ``python-multipart``.
    """
    photos = [((f.filename or f"photo{i}.png"), await f.read()) for i, f in enumerate(files)]
    return _generate_from_photos(
        name, photos, occasion=occasion, chapters=chapters, bridges=bridges,
        pipeline=_tenant_pipeline(tenant),
    )


# ── Async job submission (submit + poll) ───────────────────────────────────────
# See the ``cinemory.jobs`` module for the job-store design and its honest
# limitation (the worker below runs in-process on the accepting instance).


def _job_storage() -> StorageBackend:
    """Storage instance a background job thread may safely read/write.

    ``FakeStorage`` (offline/tests) is pure in-memory with no remote substrate
    — a FRESH instance here would be invisible to request threads (including
    this same process's own ``GET /reels/jobs/{job_id}`` reads), so the shared
    module-level ``_storage`` is reused; its plain dict/list mutations are safe
    to share across threads under the GIL (no read-modify-write cycle).

    ``B2Storage`` (live) is different: it keeps a mutable local ``index`` list
    plus a remote read-modify-write merge on every ``put`` (a small race
    already documented and accepted in ``b2_storage.py`` for independent
    writers). Sharing the SAME Python object — and its local ``index`` list —
    between this background thread and request-serving threads would add an
    avoidable extra race on top of that one (a shared list can be reassigned by
    one thread while another thread is mid-iteration over the old reference —
    a lost update, distinct from the already-accepted remote-merge race). So
    live mode gets its own fresh ``B2Storage`` per job; its constructor
    re-reads the bucket's ``index.jsonl``, so nothing is lost — the bucket, not
    the Python object, is the source of truth, and this is the exact
    multi-writer pattern the adapter's own test suite already proves safe
    (independent ``B2Storage`` instances against one bucket merge by key
    rather than clobbering each other).
    """
    if isinstance(_storage, FakeStorage):
        return _storage
    return config.build_storage()  # pragma: no cover - exercised only in live mode


def _job_pipeline(storage: StorageBackend) -> ReelPipeline:
    """The pipeline a background job thread runs its generation against.

    Unlike storage, the provider/stitcher have no cross-request visibility
    requirement (nothing else ever reads them back by reference), so a fresh
    instance is always built — this keeps ``GenblazeMediaProvider.last_manifest``
    and ``FakeMediaProvider.calls`` (both mutated per call, on the instance)
    from ever being shared between this background thread and the module-level
    synchronous pipeline's provider.
    """
    return ReelPipeline(config.build_provider(), storage, stitcher=config.build_stitcher())


def _tenant_job_storage(uid: str | None) -> StorageBackend:
    """Like ``_tenant_storage``, but for the background-job worker thread.

    GUEST (``uid is None``) returns EXACTLY ``_job_storage()`` — the identical
    call the pre-multitenancy worker always made (see that function's own
    docstring for why the background thread needs its own storage instance in
    live mode). An authed uid wraps that SAME choice with the tenant prefix,
    so a tenant's jobs live under their own prefix too and only ever poll
    their own (``jobs/<id>/status.json`` becomes
    ``tenants/<uid>/jobs/<id>/status.json``).
    """
    if uid is None:
        return _job_storage()
    return _TenantScopedStorage(_job_storage(), _tenant_prefix(uid))


def _tenant_pipeline(uid: str | None) -> ReelPipeline:
    """The pipeline a request runs its generation against.

    GUEST (``uid is None``) returns the EXACT module-level ``_pipeline`` — the
    same object every request already used before multitenancy (including
    tests that monkeypatch ``api._pipeline`` directly). Passing that object
    explicitly into ``_run_reel`` is byte-identical to the pre-multitenancy
    call ``_run_reel(spec)`` — see ``_run_reel``'s own ``pipeline or
    _pipeline`` fallback: an explicitly-passed ``_pipeline`` and an omitted
    argument resolve to the identical object. An authed uid gets a fresh
    pipeline isolated to that tenant's storage prefix, reusing
    ``_job_pipeline``'s construction shape.
    """
    if uid is None:
        return _pipeline
    return _job_pipeline(_tenant_storage(uid))


def _run_job(job_id: str, spec: ReelSpec, uid: str | None = None) -> None:
    """Background worker thread: run the generation, updating the stored status.

    Runs the SAME honest-degrade path the synchronous endpoints use
    (``_run_reel``), against an isolated pipeline/storage (see
    ``_job_storage``/``_job_pipeline``) so this thread never mutates state a
    request thread also touches. Never raises out of the thread and never
    produces an HTTP 500 for a generation failure: caught here and recorded as
    status ``failed`` with the exception CLASS NAME only (mirrors
    ``_run_reel``'s ``degrade_reason``) — the full traceback goes to the log.

    ``uid``: the verified tenant id for a tenant-scoped submission, or
    ``None`` for guest — the exact, unchanged behaviour this function always
    had (every statement below is identical to before multitenancy existed
    when ``uid is None``).
    """
    storage = _job_storage() if uid is None else _tenant_job_storage(uid)
    try:
        jobs.mark_running(storage, job_id)
        result = _run_reel(spec, _job_pipeline(storage))
        jobs.mark_done(storage, job_id, result)
    except Exception as exc:
        _log.exception("background reel job %r failed", job_id)
        jobs.mark_failed(storage, job_id, exc)


@app.post("/reels/jobs", status_code=202)
def create_reel_job(
    req: UploadReelRequest, tenant: Annotated[str | None, Depends(get_tenant)]
) -> dict:
    """Submit a reel generation as a background job; poll ``GET /reels/jobs/{id}``.

    Accepts the IDENTICAL body as ``POST /reels/upload`` — same decoding, same
    ingest validation, same 400s for a bad request — but returns immediately
    (202) with a job id instead of blocking for the full generation. See the
    module docstring and ``cinemory.jobs`` for why (edge proxy timeouts) and
    for the honest limitation of the in-process worker.

    GUEST (``tenant is None``) is byte-identical to before multitenancy:
    ``_tenant_job_storage(None)`` is exactly ``_job_storage()`` and
    ``_run_job(job_id, spec, None)`` runs the exact original job body.
    """
    photos = _decode_photos(req.photos)
    spec = _build_spec(
        req.name, photos, occasion=req.occasion, chapters=req.chapters, bridges=req.bridges
    )
    job_id = jobs.new_job_id()
    jobs.create(_tenant_job_storage(tenant), job_id)
    threading.Thread(
        target=_run_job, args=(job_id, spec, tenant), daemon=True, name=f"cinemory-job-{job_id}"
    ).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/reels/jobs/{job_id}")
def get_reel_job(
    job_id: str, tenant: Annotated[str | None, Depends(get_tenant)]
) -> dict:
    """Poll a submitted job's status.

    404 for an unknown job id. A stored-but-unreadable status object degrades
    to the identical 404 (see ``cinemory.jobs.read``) rather than a 500 — from
    the caller's side an unreadable job and a nonexistent one are the same
    "nothing to show" answer.

    Tenant-scoped the same way ``create_reel_job`` writes: a tenant's jobs
    live under their own prefix (see ``_tenant_job_storage``), so polling a
    known job id under someone else's tenant (or as guest) resolves to no
    object under THIS caller's prefix — the identical 404 as an unknown id.
    GUEST (``tenant is None``) reads via ``_tenant_storage(None)``, which is
    exactly the module-level ``_storage`` — byte-identical to before.
    """
    status = jobs.read(_tenant_storage(tenant), job_id)
    if status is None:
        raise HTTPException(404, f"no job {job_id!r}")
    return status


def _reel_index_match(
    name: str, *, kind: str, suffix: str, storage: StorageBackend | None = None
) -> dict | None:
    """Resolve a reel's stored object row from the durable index.

    Shared by ``GET /reels/{name}`` (manifest) and ``GET /reels/{name}/video``
    (playback). Content-addressed keys embed the hash, so the lookup scans the
    index. The index is re-read first so a fresh (scale-to-zero, multi-instance)
    worker that never saw the write still resolves the reel — FakeStorage has no
    remote index to reload; B2Storage re-reads ``index.jsonl`` from the bucket.
    The prefix applies the same sanitisation used when the key was written
    (``keys.make_key``), so lookups stay consistent for every reel name — and a
    traversal-shaped name can never probe outside its own sanitised prefix.

    ``storage`` defaults to the module-level ``_storage`` (the exact original
    behaviour) when omitted; a caller passes a tenant-scoped storage to scan
    only that tenant's own rows (see ``_tenant_storage``).
    """
    storage = _storage if storage is None else storage
    if not hasattr(storage, "index"):  # pragma: no cover - defensive
        return None
    reload_index = getattr(storage, "reload_index", None)
    if callable(reload_index):
        reload_index()
    from .keys import safe_component

    prefix = f"{safe_component(name)}/{kind}/"
    return next((r for r in storage.index
                 if r["key"].startswith(prefix) and r["key"].endswith(suffix)), None)


@app.get("/reels/{name}")
def get_reel(name: str, tenant: Annotated[str | None, Depends(get_tenant)]) -> dict:
    storage = _tenant_storage(tenant)
    match = _reel_index_match(name, kind="manifests", suffix="/manifest.json", storage=storage)
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    return json.loads(storage.get(match["key"]))


@app.get("/reels/{name}/video")
def get_reel_video(name: str, tenant: Annotated[str | None, Depends(get_tenant)]) -> Response:
    """Play back a stored reel through a stable, expiry-proof API URL.

    The bucket is private, so the canonical storage URL recorded in provenance
    is not directly fetchable by a browser. This route resolves the reel object
    via the durable index (the same lookup as ``GET /reels/{name}``) and returns
    the video: a **302 redirect to a FRESH presigned GET URL** when the storage
    backend can mint one (live B2), else the **bytes streamed straight from the
    store** (offline FakeStorage). Presigned URLs are minted per request and
    never persisted — manifests keep the canonical storage URL and hashes
    untouched, so provenance stays canonical.
    """
    storage = _tenant_storage(tenant)
    match = _reel_index_match(name, kind="reels", suffix="/reel.mp4", storage=storage)
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    get_url = getattr(storage, "get_url", None)
    if callable(get_url):
        return RedirectResponse(url=get_url(match["key"]), status_code=302)
    try:
        data = storage.get(match["key"])
    except Exception as exc:  # pragma: no cover - index row without object
        raise HTTPException(404, f"reel object missing for {name!r}") from exc
    return Response(content=data, media_type=match.get("content_type") or "video/mp4")


def _artifact_fetcher(
    name: str, storage: StorageBackend | None = None
) -> Callable[[str], bytes | None]:
    """A ``fetch_bytes(logical)`` closure over a reel's stored artifacts, for
    :func:`~cinemory.provenance.verify_all`.

    The durable index is reloaded ONCE (so a fresh scale-to-zero / multi-instance
    worker that never saw the write still resolves the reel — B2Storage re-reads
    ``index.jsonl``; FakeStorage has no remote index), then every artifact is
    resolved from the in-memory catalogue. Never raises: an absent artifact or a
    read error yields ``None`` so a single verification check degrades to
    ``passed: false`` rather than 500-ing the whole receipt.

    Logical names: ``reel``, ``provenance_reel``, ``clip:<sha256>`` (a per-step
    clip) and ``photo:<sha256>`` (a cited source photo). The prefix applies the
    same sanitisation used when the key was written, so a traversal-shaped name
    can never probe outside its own sanitised prefix.

    ``storage`` defaults to the module-level ``_storage`` (the exact original
    behaviour) when omitted; a caller passes a tenant-scoped storage so every
    artifact resolved here comes only from that tenant's own rows.
    """
    storage = _storage if storage is None else storage
    from .keys import safe_component

    index: list[dict] = []
    if hasattr(storage, "index"):
        reload_index = getattr(storage, "reload_index", None)
        if callable(reload_index):
            reload_index()
        index = list(storage.index)
    prefix = safe_component(name)

    def _match(kind: str, *, suffix: str | None = None, sha: str | None = None) -> dict | None:
        kpfx = f"{prefix}/{kind}/"
        for row in index:
            key = row["key"]
            if not key.startswith(kpfx):
                continue
            if suffix is not None and not key.endswith(suffix):
                continue
            if sha is not None and f"/{sha}/" not in key:
                continue
            return row
        return None

    def fetch(logical: str) -> bytes | None:
        if logical == "reel":
            row = _match("reels", suffix="/reel.mp4")
        elif logical == "provenance_reel":
            row = _match("reels", suffix="/reel.provenance.mp4")
        elif logical.startswith("clip:"):
            row = _match("clips", sha=logical[len("clip:"):])
        elif logical.startswith("photo:"):
            row = _match("photos", sha=logical[len("photo:"):])
        else:
            return None
        if not row:
            return None
        try:
            return storage.get(row["key"])
        except Exception:  # pragma: no cover - index row without a live object
            return None

    return fetch


@app.get("/reels/{name}/verify")
def verify_reel(name: str, tenant: Annotated[str | None, Depends(get_tenant)]) -> dict:
    """Server-side re-verification of a sealed reel as a named-check receipt.

    Re-fetches the manifest + every recorded artifact from the store and re-runs
    each check from those bytes (:func:`~cinemory.provenance.verify_all`): the
    seal, the reel / provenance-reel / per-step-clip hashes, the embedded-manifest
    equality, and the structural invariants (every step asset present, every
    source-photo citation resolvable, provider/model named). Honest-degrade: a
    genuinely missing reel is a 404; unreadable manifest bytes still return a
    fully-shaped FAILING receipt (never a 500), with failing checks doing the
    talking.
    """
    storage = _tenant_storage(tenant)
    match = _reel_index_match(name, kind="manifests", suffix="/manifest.json", storage=storage)
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    try:
        manifest = json.loads(storage.get(match["key"]))
    except Exception:  # unreadable bytes → a fully-shaped failing receipt, not a 500
        manifest = {}
    return verify_all(manifest, _artifact_fetcher(name, storage)).to_dict()


@app.get("/me/library")
def get_my_library(tenant: Annotated[str | None, Depends(get_tenant)]) -> dict:
    """List the authed tenant's own reels, from THEIR tenant-scoped index only.

    401 for guest (``tenant is None``) — this route only ever makes sense for
    an authenticated caller. The listing is isolated by construction: a
    ``_TenantScopedStorage.index`` scan can physically only contain rows under
    this caller's own ``tenants/<uid>/`` prefix (see that class's docstring),
    so this can never leak another tenant's — or a guest's — reels.
    """
    if tenant is None:
        raise HTTPException(401, "sign in required")
    storage = _tenant_storage(tenant)
    reload_index = getattr(storage, "reload_index", None)
    if callable(reload_index):
        reload_index()

    reels: list[dict] = []
    for row in storage.index:
        key = row["key"]
        parts = key.split("/")
        if len(parts) < 2 or parts[1] != "manifests" or not key.endswith("/manifest.json"):
            continue
        entry: dict = {
            "reel_name": parts[0], "manifest_hash": None,
            "created_at": None, "updated_at": None,
        }
        try:
            manifest = json.loads(storage.get(key))
        except Exception:  # unreadable manifest → still list the reel, best-effort
            manifest = None
        if isinstance(manifest, dict):
            entry["manifest_hash"] = manifest.get("manifest_hash")
            steps = [s for s in (manifest.get("steps") or []) if isinstance(s, dict)]
            starts = [s["started_at"] for s in steps if s.get("started_at")]
            finishes = [s["finished_at"] for s in steps if s.get("finished_at")]
            if starts:
                entry["created_at"] = min(starts)
            if finishes:
                entry["updated_at"] = max(finishes)
        reels.append(entry)
    return {"reels": reels}


@app.delete("/me/data")
def delete_my_data(tenant: Annotated[str | None, Depends(get_tenant)]) -> dict:
    """Delete every object under the authed tenant's own storage prefix.

    401 for guest (``tenant is None``). The deletion is STRUCTURALLY scoped:
    ``storage`` is a ``_TenantScopedStorage`` built from the VERIFIED uid (see
    ``_tenant_storage``/``_tenant_prefix``), so every key this loop can ever
    construct is ``tenants/<uid>/<key>`` — there is no code path here that can
    address a guest key (no prefix) or another tenant's prefix. Deleting each
    key also removes its row from the BASE storage's own index (see
    ``FakeStorage.delete``/``B2Storage.delete``), so this tenant's ``index``
    (and therefore ``/me/library``) is empty afterward with no separate
    index-cleanup step needed.
    """
    if tenant is None:
        raise HTTPException(401, "sign in required")
    storage = _tenant_storage(tenant)
    reload_index = getattr(storage, "reload_index", None)
    if callable(reload_index):
        reload_index()
    keys = [row["key"] for row in storage.index]  # materialise before mutating
    for key in keys:
        storage.delete(key)
    return {"deleted": len(keys)}


# Serve the compiled web client from the same origin as the API, so a single
# Cloud Run container serves both. Mounted LAST and guarded by directory
# existence: the explicit API routes above take precedence, and local/CI runs
# (where the client isn't built) are unaffected. Set CINEMORY_WEB_DIR to the
# folder holding index.html + dist/ (the Docker image sets it to /app/web).
_WEB_DIR = Path(os.environ.get("CINEMORY_WEB_DIR", "")).expanduser()
if _WEB_DIR.is_dir() and (_WEB_DIR / "index.html").is_file():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")


def main() -> None:  # pragma: no cover - manual entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
