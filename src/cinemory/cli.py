"""Cinemory CLI — generate a reel from synthetic photos end to end.

    python -m cinemory.cli --name demo --chapters 3 --per-chapter 2 --out ./out

Runs offline by default (fakes). Set CINEMORY_MODE=live for real Genblaze + B2.
Writes the reel + embedded-provenance reel + manifest.json locally for inspection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from .keys import KeyStrategy, make_key
from .models import Bridge
from .pipeline import ReelPipeline
from .provenance import extract, verify_asset, verify_manifest
from .synthetic import synth_reel_spec


def build_pipeline() -> tuple[ReelPipeline, object]:
    storage = config.build_storage()
    pipeline = ReelPipeline(config.build_provider(), storage, stitcher=config.build_stitcher())
    return pipeline, storage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cinemory")
    ap.add_argument("--name", default="demo-reel")
    ap.add_argument("--chapters", type=int, default=3)
    ap.add_argument("--per-chapter", type=int, default=2)
    ap.add_argument("--occasion", default="anniversary",
                    help="occasion preset: anniversary | graduation | birthday | "
                         "wedding | year-in-review | business-event")
    ap.add_argument("--bridges", action="store_true", help="add chapter-to-chapter bridges")
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args(argv)

    spec = synth_reel_spec(args.name, chapters=args.chapters, per_chapter=args.per_chapter,
                           occasion=args.occasion)
    if args.bridges:
        for i in range(len(spec.chapters) - 1):
            spec.bridges.append(
                Bridge(from_chapter=spec.chapters[i].id, to_chapter=spec.chapters[i + 1].id,
                       prompt="smooth match-cut transition"))

    pipeline, storage = build_pipeline()
    result = pipeline.run(spec)

    args.out.mkdir(parents=True, exist_ok=True)
    reel_key = make_key(KeyStrategy.HIERARCHICAL, reel=args.name, kind="reels",
                        sha256=result.reel_asset.sha256, name="reel.mp4")
    reel_bytes = storage.get(reel_key)
    (args.out / "reel.mp4").write_bytes(reel_bytes)

    manifest_key = next(r["key"] for r in storage.index
                        if r["key"].startswith(f"{args.name}/manifests/"))
    manifest = json.loads(storage.get(manifest_key))
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    prov_key = next(r["key"] for r in storage.index
                    if r["key"].endswith("reel.provenance.mp4"))
    prov_bytes = storage.get(prov_key)
    (args.out / "reel.provenance.mp4").write_bytes(prov_bytes)

    # Verify provenance offline.
    ok_manifest = verify_manifest(manifest)
    ok_asset = verify_asset(manifest, reel_key, reel_bytes)
    ok_embedded = verify_manifest(extract(prov_bytes) or {})

    print(f"reel:            {result.reel_asset.url}")
    print(f"reel sha256:     {result.reel_asset.sha256}")
    print(f"manifest:        {result.manifest_uri}")
    print(f"manifest hash:   {result.manifest_hash}")
    print(f"steps:           {len(result.steps)}")
    print(f"stored objects:  {len(storage.index)}")
    print(f"verify manifest: {ok_manifest}")
    print(f"verify asset:    {ok_asset}")
    print(f"verify embedded: {ok_embedded}")
    print(f"written to:      {args.out.resolve()}")
    return 0 if (ok_manifest and ok_asset and ok_embedded) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
