"""Reel orchestration.

Maps the cinemory *concept* (photo -> I2V clip; chapter-to-chapter FLF2V bridge;
ffmpeg stitch; music-driven cuts) onto Genblaze-style generative steps, then
seals the run with verifiable provenance and persists every artifact to B2.

The orchestrator depends only on ports (``MediaProvider``, ``StorageBackend``,
``Stitcher``), so the exact same code path runs against the real Genblaze/B2
adapters or the offline fakes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .keys import KeyStrategy, make_key
from .models import Asset, Modality, ReelResult, ReelSpec, StepRecord
from .ports import MediaProvider, Stitcher, StorageBackend
from .provenance import build_manifest, embed, sha256_bytes
from .stitch import FakeStitcher


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReelPipeline:
    def __init__(
        self,
        provider: MediaProvider,
        storage: StorageBackend,
        *,
        stitcher: Stitcher | None = None,
        key_strategy: KeyStrategy = KeyStrategy.HIERARCHICAL,
        image_model: str = "seedream-5.0-lite",
        video_model: str = "Kling-Image2Video-V2.1-Master",
        bridge_model: str = "seedance-2-0-260128",
    ) -> None:
        self.provider = provider
        self.storage = storage
        self.stitcher = stitcher or FakeStitcher()
        self.key_strategy = key_strategy
        self.image_model = image_model
        self.video_model = video_model
        self.bridge_model = bridge_model

    # ── storage helpers ──────────────────────────────────────────────────────
    def _store(self, reel: str, kind: str, name: str, data: bytes, content_type: str) -> Asset:
        digest = sha256_bytes(data)
        key = make_key(self.key_strategy, reel=reel, kind=kind, sha256=digest, name=name)
        url = self.storage.put(key, data, content_type=content_type)
        modality = {"photos": Modality.IMAGE, "clips": Modality.VIDEO,
                    "reels": Modality.VIDEO, "manifests": Modality.TEXT}.get(kind, Modality.VIDEO)
        return Asset(modality=modality, sha256=digest, size_bytes=len(data), url=url, filename=name)

    def _step(self, *, model: str, prompt: str, modality: Modality,
              inputs: list[bytes], params: dict, reel: str, kind: str, name: str) -> StepRecord:
        started = _now()
        data = self.provider.generate(model=model, prompt=prompt, modality=modality,
                                       inputs=inputs, params=params)
        finished = _now()
        asset = self._store(reel, kind, name, data, "video/mp4")
        return StepRecord(provider=self.provider.name, model=model, prompt=prompt,
                          modality=modality, params=params, started_at=started,
                          finished_at=finished, asset=asset)

    # ── main ─────────────────────────────────────────────────────────────────
    def run(self, spec: ReelSpec) -> ReelResult:
        reel = spec.name
        steps: list[StepRecord] = []
        clips: list[bytes] = []

        # 1. Persist synthetic inputs to B2 (input provenance).
        for chapter in spec.chapters:
            for photo in chapter.photos:
                self._store(reel, "photos", photo.filename, photo.data, "image/png")

        # 2. Photo -> video clip (image-to-video), one per photo.
        for chapter in spec.chapters:
            for photo in chapter.photos:
                rec = self._step(
                    model=self.video_model, prompt=chapter.prompt, modality=Modality.VIDEO,
                    inputs=[photo.data], params={"aspect_ratio": spec.aspect_ratio,
                                                 "chapter": chapter.id},
                    reel=reel, kind="clips", name=f"{chapter.id}_{photo.filename}.mp4",
                )
                steps.append(rec)
                clips.append(self.storage.get(
                    make_key(self.key_strategy, reel=reel, kind="clips",
                             sha256=rec.asset.sha256, name=rec.asset.filename)))

        # 3. First-last-frame bridges between chapters.
        for bridge in spec.bridges:
            frm = next((c for c in spec.chapters if c.id == bridge.from_chapter), None)
            to = next((c for c in spec.chapters if c.id == bridge.to_chapter), None)
            if frm and to and frm.photos and to.photos:
                rec = self._step(
                    model=self.bridge_model, prompt=bridge.prompt, modality=Modality.VIDEO,
                    inputs=[frm.photos[-1].data, to.photos[0].data],
                    params={"kind": "flf2v", "from": frm.id, "to": to.id},
                    reel=reel, kind="clips", name=f"bridge_{frm.id}_{to.id}.mp4",
                )
                steps.append(rec)
                clips.append(self.storage.get(
                    make_key(self.key_strategy, reel=reel, kind="clips",
                             sha256=rec.asset.sha256, name=rec.asset.filename)))

        # 4. Stitch into the final reel.
        reel_bytes = self.stitcher.stitch(clips)
        reel_asset = self._store(reel, "reels", "reel.mp4", reel_bytes, "video/mp4")

        result = ReelResult(reel_name=reel, reel_asset=reel_asset, steps=steps)

        # 5. Seal provenance and persist manifest to B2, then embed it in the reel.
        manifest = build_manifest(result)
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        manifest_asset = self._store(reel, "manifests", "manifest.json",
                                     manifest_bytes, "application/json")
        result.manifest_uri = manifest_asset.url
        result.manifest_hash = manifest["manifest_hash"]

        embedded = embed(reel_bytes, manifest)
        self._store(reel, "reels", "reel.provenance.mp4", embedded, "video/mp4")
        return result
