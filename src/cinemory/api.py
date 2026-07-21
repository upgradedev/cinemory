"""Cinemory HTTP API (FastAPI).

Routes:
  GET  /health           liveness + active mode
  GET  /occasions        list selectable occasion presets (themes)
  POST /reels            generate a reel from a synthetic spec, return provenance
  POST /reels/upload     generate a reel from real uploaded photos (base64 JSON)
  POST /reels/upload-multipart
                         generate a reel from real uploaded photos (multipart)
  GET  /reels/{name}     fetch the stored provenance manifest for a reel
  GET  /reels/{name}/video
                         play back the stored reel (302 to a fresh presigned
                         URL in live mode; streamed bytes offline)

The API is storage/provider agnostic (see ``config``): offline by default so it
boots and serves with no credentials. In ``live`` mode it uses the real
Genblaze/B2 backends only when their credentials are present, otherwise it
transparently degrades to the offline path — so reel generation never 500s.
The same contract holds per request: when the live provider fails mid-request,
the reel is regenerated with the offline provider (storage unchanged) and the
response says so honestly (``provider_degraded`` + the actual ``provider``,
which the sealed manifest also records per step).
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from . import config
from .adapters import FakeMediaProvider
from .ingest import IngestError, build_spec_from_photos
from .models import ReelResult, ReelSpec
from .occasions import list_occasions
from .pipeline import ReelPipeline
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
    }


def _run_reel(spec: ReelSpec) -> dict:
    """Run the pipeline; degrade THIS request honestly if the live provider fails.

    The core action must never 500 because a remote generation backend
    misbehaved: on a live-provider failure the same spec is regenerated with
    the offline provider against the *same* storage (real B2 in live mode).
    Nothing lies about it — the response carries ``provider_degraded: true``
    plus the provider that actually generated, and the sealed manifest records
    that provider on every step. A failure of the offline provider itself is a
    genuine bug and propagates (500) rather than being masked.
    """
    try:
        body = _reel_response(_pipeline.run(spec))
        body["provider"] = _pipeline.provider.name
        body["provider_degraded"] = False
        return body
    except HTTPException:
        raise
    except Exception as exc:
        if isinstance(_pipeline.provider, FakeMediaProvider):
            raise
        _log.exception(
            "live media provider %r failed for reel %r; regenerating this "
            "request with the offline provider (storage unchanged)",
            _pipeline.provider.name,
            spec.name,
        )
        # The offline provider's deterministic clips are not decodable video,
        # so the regeneration pairs it with the offline stitcher (a real
        # ffmpeg stitcher would fail on them) — the exact offline generation
        # path, persisted to whatever storage the deployment actually uses.
        fallback = ReelPipeline(FakeMediaProvider(), _storage, stitcher=FakeStitcher())
        body = _reel_response(fallback.run(spec))
        body["provider"] = fallback.provider.name
        body["provider_degraded"] = True
        # Class name only — exception text may embed URLs/identifiers that do
        # not belong in an API response; the full traceback is in the log.
        body["degrade_reason"] = type(exc).__name__
        return body


def _generate_from_photos(
    name: str, photos: list[tuple[str, bytes]], *, occasion: str, chapters: int, bridges: bool
) -> dict:
    """Shared ingest path for both upload endpoints (base64 + multipart)."""
    try:
        spec = build_spec_from_photos(
            name, photos, occasion=occasion, chapters=chapters, bridges=bridges
        )
    except IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _run_reel(spec)


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
    }


@app.get("/occasions")
def occasions() -> dict:
    return {"occasions": list_occasions()}


@app.post("/reels")
def create_reel(req: ReelRequest) -> dict:
    spec = synth_reel_spec(req.name, chapters=req.chapters, per_chapter=req.per_chapter,
                           occasion=req.occasion)
    return _run_reel(spec)


@app.post("/reels/upload")
def upload_reel(req: UploadReelRequest) -> dict:
    """Generate a reel from real photo bytes sent as base64 JSON.

    This is the dependency-free ingest path the mobile/web client uses to send
    actual pixels; the decoded photos flow through the same storage + pipeline as
    the synthetic demo, sealing real SHA-256 provenance.
    """
    photos: list[tuple[str, bytes]] = []
    for i, p in enumerate(req.photos):
        try:
            data = base64.b64decode(p.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(400, f"photo {i} is not valid base64") from exc
        photos.append((p.filename or f"photo{i}.png", data))
    return _generate_from_photos(
        req.name, photos, occasion=req.occasion, chapters=req.chapters, bridges=req.bridges
    )


@app.post("/reels/upload-multipart")
async def upload_reel_multipart(
    files: Annotated[list[UploadFile], File()],
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
        name, photos, occasion=occasion, chapters=chapters, bridges=bridges
    )


def _reel_index_match(name: str, *, kind: str, suffix: str) -> dict | None:
    """Resolve a reel's stored object row from the durable index.

    Shared by ``GET /reels/{name}`` (manifest) and ``GET /reels/{name}/video``
    (playback). Content-addressed keys embed the hash, so the lookup scans the
    index. The index is re-read first so a fresh (scale-to-zero, multi-instance)
    worker that never saw the write still resolves the reel — FakeStorage has no
    remote index to reload; B2Storage re-reads ``index.jsonl`` from the bucket.
    The prefix applies the same sanitisation used when the key was written
    (``keys.make_key``), so lookups stay consistent for every reel name — and a
    traversal-shaped name can never probe outside its own sanitised prefix.
    """
    if not hasattr(_storage, "index"):  # pragma: no cover - defensive
        return None
    reload_index = getattr(_storage, "reload_index", None)
    if callable(reload_index):
        reload_index()
    from .keys import safe_component

    prefix = f"{safe_component(name)}/{kind}/"
    return next((r for r in _storage.index
                 if r["key"].startswith(prefix) and r["key"].endswith(suffix)), None)


@app.get("/reels/{name}")
def get_reel(name: str) -> dict:
    match = _reel_index_match(name, kind="manifests", suffix="/manifest.json")
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    return json.loads(_storage.get(match["key"]))


@app.get("/reels/{name}/video")
def get_reel_video(name: str) -> Response:
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
    match = _reel_index_match(name, kind="reels", suffix="/reel.mp4")
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    get_url = getattr(_storage, "get_url", None)
    if callable(get_url):
        return RedirectResponse(url=get_url(match["key"]), status_code=302)
    try:
        data = _storage.get(match["key"])
    except Exception as exc:  # pragma: no cover - index row without object
        raise HTTPException(404, f"reel object missing for {name!r}") from exc
    return Response(content=data, media_type=match.get("content_type") or "video/mp4")


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
