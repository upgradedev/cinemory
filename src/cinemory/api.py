"""MemoryReel HTTP API (FastAPI).

Routes:
  GET  /health           liveness + active mode
  GET  /occasions        list selectable occasion presets (themes)
  POST /reels            generate a reel from a synthetic spec, return provenance
  POST /reels/upload     generate a reel from real uploaded photos (base64 JSON)
  POST /reels/upload-multipart
                         generate a reel from real uploaded photos (multipart)
  GET  /reels/{name}     fetch the stored provenance manifest for a reel

The API is storage/provider agnostic (see ``config``): offline by default so it
boots and serves with no credentials. In ``live`` mode it uses the real
Genblaze/B2 backends only when their credentials are present, otherwise it
transparently degrades to the offline path — so reel generation never 500s.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import config
from .ingest import IngestError, build_spec_from_photos
from .models import ReelResult
from .occasions import list_occasions
from .pipeline import ReelPipeline
from .synthetic import synth_reel_spec

app = FastAPI(title="MemoryReel API", version="0.1.0")

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
        "reel_url": result.reel_asset.url,
        "reel_sha256": result.reel_asset.sha256,
        "manifest_uri": result.manifest_uri,
        "manifest_hash": result.manifest_hash,
        "steps": len(result.steps),
    }


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
    result = _pipeline.run(spec)
    return _reel_response(result)


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
    result = _pipeline.run(spec)
    return _reel_response(result)


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


@app.get("/reels/{name}")
def get_reel(name: str) -> dict:
    # Content-addressed keys embed the hash; scan the index for this reel/manifest.
    if not hasattr(_storage, "index"):  # pragma: no cover - live path
        raise HTTPException(404, "manifest lookup requires an indexed store")
    match = next((r for r in _storage.index
                  if r["key"].startswith(f"{name}/manifests/")), None)
    if not match:
        raise HTTPException(404, f"no reel named {name!r}")
    return json.loads(_storage.get(match["key"]))


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
