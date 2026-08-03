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
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

from . import failures
from .keys import KeyStrategy, make_key
from .models import Asset, Modality, ReelResult, ReelSpec, StepRecord
from .ports import MediaProvider, Stitcher, StorageBackend
from .provenance import build_manifest, embed, sha256_bytes
from .stitch import FakeStitcher
from .usage import CallUsage, RunUsage

_log = logging.getLogger("cinemory.pipeline")


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    """An operator override, clamped and never able to break the boot."""
    try:
        return max(minimum, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


#: How many generation calls may be in flight at once.
#:
#: Chosen, not measured: the provider's real concurrency limit is not published
#: to us and we are not going to discover it by firing paid calls at it until
#: it complains. So this is set to the most photos one reel can hold, which
#: means a reel is at most one wave of calls and a SECOND reel generating at
#: the same time doubles it rather than multiplying it. In absolute terms five
#: simultaneous calls is a small number for a hosted inference API, which is
#: why it is a safe place to start; it is deliberately conservative and
#: deliberately not tuned upward on a hunch.
#:
#: If the provider does push back, that is handled rather than hoped away: a
#: rate-limited call backs off and retries (see ``_generate``), and
#: ``CINEMORY_MAX_CONCURRENT_GENERATIONS`` can drop this to 1 without a deploy,
#: which restores exactly the sequential behaviour this pipeline had before.
MAX_CONCURRENT_GENERATIONS = _env_int("CINEMORY_MAX_CONCURRENT_GENERATIONS", 5)

#: Total attempts for a call the provider rate-limits, the first included.
#: Three, because the point is to ride out a brief limit, not to keep a visitor
#: waiting: with the base delay below, the worst case adds well under a minute
#: to a call that already takes minutes.
RATE_LIMIT_MAX_ATTEMPTS = _env_int("CINEMORY_RATE_LIMIT_MAX_ATTEMPTS", 3)

#: First backoff step, doubled per attempt, plus up to one extra step of
#: jitter so a whole wave limited at the same instant does not march back in
#: lockstep and limit itself again.
RATE_LIMIT_BASE_DELAY_SECONDS = float(
    os.environ.get("CINEMORY_RATE_LIMIT_BASE_DELAY_SECONDS") or 5.0
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class _Generated:
    """The result of one provider call, before anything is stored.

    Kept separate from :class:`~cinemory.models.StepRecord` because generation
    and storage are now separate phases: this is what a worker thread produces,
    and the main thread turns it into a sealed step in spec order.
    """

    data: bytes
    started_at: str
    finished_at: str
    elapsed_seconds: float
    attempts: int


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
    def _store(self, reel: str, kind: str, name: str, data: bytes, content_type: str,
               usage: RunUsage | None = None) -> Asset:
        digest = sha256_bytes(data)
        key = make_key(self.key_strategy, reel=reel, kind=kind, sha256=digest, name=name)
        url = self.storage.put(key, data, content_type=content_type)
        if usage is not None:
            usage.record_object(len(data))
        modality = {"photos": Modality.IMAGE, "clips": Modality.VIDEO,
                    "reels": Modality.VIDEO, "manifests": Modality.TEXT}.get(kind, Modality.VIDEO)
        return Asset(modality=modality, sha256=digest, size_bytes=len(data), url=url, filename=name)

    # ── generation ───────────────────────────────────────────────────────────
    def _generate(self, *, model: str, prompt: str, modality: Modality,
                  inputs: list[bytes], params: dict) -> _Generated:
        """One provider call, with a bounded backoff for a rate limit.

        Deliberately does NO storage. That split is what makes the concurrency
        below safe: this half is a remote call that holds no shared state and
        can run in a worker thread, while writing to storage stays on the main
        thread in deterministic order (see ``run``).

        Retries ONLY a rate limit (see ``failures.is_retryable``): the provider
        saying "not right now" is the one failure that answers to waiting. Every
        other failure propagates immediately to the caller's honest fallback
        rather than spending a visitor's waiting window on an answer that will
        not change.
        """
        started = _now()
        began = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                data = self.provider.generate(model=model, prompt=prompt, modality=modality,
                                              inputs=inputs, params=params)
                break
            except Exception as exc:
                if attempt > RATE_LIMIT_MAX_ATTEMPTS - 1 or not failures.is_retryable(exc):
                    raise
                # Exponential, with jitter so a whole wave of calls rate-limited
                # at the same instant does not march back in lockstep and
                # rate-limit itself again.
                delay = RATE_LIMIT_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
                delay += random.uniform(0, RATE_LIMIT_BASE_DELAY_SECONDS)
                _log.warning(
                    "provider %r rate-limited generating with %r (attempt %d/%d); "
                    "backing off %.1fs",
                    self.provider.name, model, attempt, RATE_LIMIT_MAX_ATTEMPTS, delay,
                )
                time.sleep(delay)
        return _Generated(
            data=data, started_at=started, finished_at=_now(),
            elapsed_seconds=time.monotonic() - began, attempts=attempt,
        )

    def _record(self, gen: _Generated, *, model: str, prompt: str, modality: Modality,
                inputs: list[bytes], params: dict, reel: str, kind: str, name: str,
                usage: RunUsage) -> StepRecord:
        """Persist a generated artifact and seal its provenance record.

        Runs on the main thread, in spec order, so storage sees exactly the
        same sequence of writes it always did and the manifest records exactly
        the same steps in the same order, whatever order the generation calls
        happened to finish in.
        """
        asset = self._store(reel, kind, name, gen.data, "video/mp4", usage=usage)
        usage.record_call(CallUsage(
            provider=self.provider.name, model=model, modality=modality.value,
            started_at=gen.started_at, finished_at=gen.finished_at,
            duration_ms=max(0, round(gen.elapsed_seconds * 1000)),
            input_bytes=sum(len(b) for b in inputs), output_bytes=len(gen.data),
            attempts=gen.attempts,
        ))
        # Cite the source photo(s): the same content-addressing hash used for
        # every stored asset, in input order (empty for a no-input step).
        source_sha256s = [sha256_bytes(b) for b in inputs]
        return StepRecord(provider=self.provider.name, model=model, prompt=prompt,
                          modality=modality, params=params, started_at=gen.started_at,
                          finished_at=gen.finished_at, asset=asset,
                          source_sha256s=source_sha256s)

    def _generate_all(self, plans: list[dict]) -> list[_Generated]:
        """Run every planned generation call, and return the results IN PLAN
        ORDER regardless of which finished first.

        The calls are independent by construction: an image-to-video step takes
        one photo, and a bridge takes the first and last PHOTOS of two chapters
        (never a generated clip), so nothing here waits on anything else here.
        Running them one after another was costing the full sum of their
        latencies for no reason.

        Order is restored by index, not by completion, so the manifest is
        byte-identical to a sequential run given the same inputs. A single
        worker (the offline provider's case, and any deployment that sets the
        bound to 1) takes the plain in-line path with no pool at all.
        """
        if len(plans) <= 1 or MAX_CONCURRENT_GENERATIONS <= 1:
            return [self._generate(**plan) for plan in plans]

        workers = min(len(plans), MAX_CONCURRENT_GENERATIONS)
        results: list[_Generated | None] = [None] * len(plans)
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cinemory-gen")
        try:
            futures = {pool.submit(self._generate, **plan): i for i, plan in enumerate(plans)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        finally:
            # Never block on calls still in flight when one has already failed.
            # The caller's honest fallback needs that failure NOW, not after
            # the remaining multi-minute renders finish; a visitor is watching
            # a bounded waiting window. Queued-but-unstarted calls are
            # cancelled outright.
            pool.shutdown(wait=False, cancel_futures=True)
        assert all(r is not None for r in results)  # every future resolved above
        return [r for r in results if r is not None]

    # ── main ─────────────────────────────────────────────────────────────────
    def run(self, spec: ReelSpec) -> ReelResult:
        from .occasions import get_occasion

        reel = spec.name
        occ = get_occasion(spec.occasion)
        steps: list[StepRecord] = []
        clips: list[bytes] = []
        usage = RunUsage(reel_name=reel)
        run_started_at = _now()
        run_began = time.monotonic()

        # 1. Persist synthetic inputs to B2 (input provenance).
        for chapter in spec.chapters:
            for photo in chapter.photos:
                self._store(reel, "photos", photo.filename, photo.data, "image/png",
                            usage=usage)

        # 2. PLAN every generative call, in the exact order the manifest must
        #    record them. Planning and running are separated so the calls can
        #    overlap (see _generate_all) while the sealed order stays a
        #    property of this list, not of who finished first.
        #
        #    a) Photo -> video clip (image-to-video), one per photo. The
        #       occasion's pacing/music direction rides on each step's params
        #       (and is thereby sealed into the manifest); the fake provider
        #       hashes only model/prompt/modality/inputs, so clip bytes stay
        #       deterministic.
        plans: list[dict] = []
        stores: list[dict] = []
        for chapter in spec.chapters:
            for photo in chapter.photos:
                plans.append({
                    "model": self.video_model, "prompt": chapter.prompt,
                    "modality": Modality.VIDEO, "inputs": [photo.data],
                    "params": {"aspect_ratio": spec.aspect_ratio, "chapter": chapter.id,
                               "target_seconds": occ.seconds_per_clip, "tempo": occ.tempo,
                               "music_style": occ.music_style},
                })
                stores.append({"kind": "clips", "name": f"{chapter.id}_{photo.filename}.mp4"})

        #    b) First-last-frame bridges between chapters. Independent of the
        #       clips above: a bridge is generated from the neighbouring
        #       chapters' PHOTOS, never from a generated clip, so it does not
        #       have to wait for (a) and joins the same wave.
        for bridge in spec.bridges:
            frm = next((c for c in spec.chapters if c.id == bridge.from_chapter), None)
            to = next((c for c in spec.chapters if c.id == bridge.to_chapter), None)
            if frm and to and frm.photos and to.photos:
                plans.append({
                    "model": self.bridge_model, "prompt": bridge.prompt,
                    "modality": Modality.VIDEO,
                    "inputs": [frm.photos[-1].data, to.photos[0].data],
                    "params": {"kind": "flf2v", "from": frm.id, "to": to.id},
                })
                stores.append({"kind": "clips", "name": f"bridge_{frm.id}_{to.id}.mp4"})

        # 3. Run them, then seal them IN PLAN ORDER. Storage stays on this
        #    thread and in this order, so the write sequence and the manifest
        #    are identical to a fully sequential run.
        usage.max_concurrency = (
            min(len(plans), MAX_CONCURRENT_GENERATIONS) if len(plans) > 1 else 1
        )
        generated = self._generate_all(plans)
        # strict: a generation result must exist for every plan, in order.
        for gen, plan, store in zip(generated, plans, stores, strict=True):
            rec = self._record(gen, reel=reel, usage=usage, **plan, **store)
            steps.append(rec)
            clips.append(self.storage.get(
                make_key(self.key_strategy, reel=reel, kind="clips",
                         sha256=rec.asset.sha256, name=rec.asset.filename)))

        # 4. Stitch into the final reel.
        reel_bytes = self.stitcher.stitch(clips)
        reel_asset = self._store(reel, "reels", "reel.mp4", reel_bytes, "video/mp4", usage=usage)

        result = ReelResult(
            reel_name=reel, reel_asset=reel_asset, steps=steps, occasion=occ.key,
            occasion_style={
                "label": occ.label,
                "music_style": occ.music_style,
                "tempo": occ.tempo,
                "seconds_per_clip": occ.seconds_per_clip,
                "transition": occ.transition,
                "title_style": occ.title_style,
                "aspect_ratio": occ.aspect_ratio,
            },
        )

        # 5. Seal provenance and persist manifest to B2, then embed it in the reel.
        manifest = build_manifest(result)
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        manifest_asset = self._store(reel, "manifests", "manifest.json",
                                     manifest_bytes, "application/json", usage=usage)
        result.manifest_uri = manifest_asset.url
        result.manifest_hash = manifest["manifest_hash"]

        embedded = embed(reel_bytes, manifest)
        self._store(reel, "reels", "reel.provenance.mp4", embedded, "video/mp4", usage=usage)

        # 6. Close the books. Recorded on the result (and so on the job status,
        #    readable per job long after the fact) AND as one greppable log
        #    line. Deliberately after the manifest is sealed: the accounting
        #    counts the manifest write too, and it is observability rather than
        #    provenance, so it is not inside the hash.
        usage.finish(
            started_at=run_started_at, finished_at=_now(),
            elapsed_seconds=time.monotonic() - run_began,
        )
        result.usage = usage
        _log.info("reel usage: %s", usage.summary_line())
        return result
