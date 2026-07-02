"""MemoryReel HTTP API (FastAPI).

Routes:
  GET  /health           liveness + active mode
  GET  /occasions        list selectable occasion presets (themes)
  POST /reels            generate a reel from a synthetic spec, return provenance
  GET  /reels/{name}     fetch the stored provenance manifest for a reel

The API is storage/provider agnostic (see ``config``): offline by default so it
boots and serves with no credentials.
"""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import config
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "cinemory-api", "mode": config.mode()}


@app.get("/occasions")
def occasions() -> dict:
    return {"occasions": list_occasions()}


@app.post("/reels")
def create_reel(req: ReelRequest) -> dict:
    spec = synth_reel_spec(req.name, chapters=req.chapters, per_chapter=req.per_chapter,
                           occasion=req.occasion)
    result = _pipeline.run(spec)
    return {
        "reel_name": result.reel_name,
        "occasion": result.occasion,
        "reel_url": result.reel_asset.url,
        "reel_sha256": result.reel_asset.sha256,
        "manifest_uri": result.manifest_uri,
        "manifest_hash": result.manifest_hash,
        "steps": len(result.steps),
    }


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


def main() -> None:  # pragma: no cover - manual entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
