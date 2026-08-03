#!/usr/bin/env python3
"""Generate the demo video's music bed — Genblaze to MiniMax Music on GMI Cloud.

The soundtrack is **generated, not licensed**. That is the whole point: a track
whose licence we cannot state precisely is a problem to hand a judge, and a
generated bed is as clearly ours as the footage. It goes through the *same*
path every other Cinemory asset takes — the :class:`MediaProvider` port, the
Genblaze ``Pipeline``, GMI Cloud — so nothing here is a side door.

Direction comes from the occasion the reel in the video actually uses, not from
a genre invented for the video. ``Occasion.music_style`` is documented as
"maps to a track/generation prompt on the live path"; this is that path. The
demo take is an **anniversary** reel (see ``demo/video-assets/reels.txt``), so
the bed is built from ``warm romantic strings`` at ``96`` BPM.

Run once; commit the result. ``demo/build-video.py`` muxes the **committed**
mp3 and never calls a provider, so the video gate and a rebuild stay offline.

    python demo/generate-music.py                     # -> video-assets/music/
    python demo/generate-music.py --occasion wedding  # a different bed

Env:  GMI_API_KEY (required)
      GENBLAZE_PROVIDER (default gmicloud)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from cinemory.adapters.genblaze_provider import (  # noqa: E402
    MINIMAX_MUSIC_MODEL,
    GenblazeMediaProvider,
)
from cinemory.models import Modality  # noqa: E402
from cinemory.occasions import OCCASIONS  # noqa: E402

DEMO = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(DEMO, "video-assets", "music")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

#: Structure tags only, no words. ``[Inst]`` is MiniMax's documented
#: instrumental-section tag, and ``lyrics`` is a REQUIRED parameter — so an
#: instrumental bed is requested by giving the model a lyric sheet that asks
#: for playing rather than singing. A vocal under the narration would be worse
#: than the silence this replaces, so the prompt also opens with the negative
#: constraint rather than burying it after the style.
INSTRUMENTAL_LYRICS = "[Intro]\n[Inst]\n[Inst]\n[Outro]"

#: MP3 at the model's top encode. The bed is muxed and re-encoded to AAC on the
#: way into the video, so this is the source master, not the shipped audio.
AUDIO_PARAMS = {"format": "mp3", "sample_rate": 44100, "bitrate": 256000}


def music_prompt(occasion) -> str:
    """The generation prompt for one occasion's bed.

    Negative constraint first (see ``INSTRUMENTAL_LYRICS``), then the
    occasion's own ``music_style`` and ``tempo`` verbatim, then the fact that
    this is underscore — music that has to sit beneath a voice without
    competing with it.
    """
    return (
        "Instrumental only, no vocals, no voice, no singing, no lyrics. "
        f"{occasion.music_style}, {occasion.tempo:.0f} beats per minute. "
        "Gentle cinematic underscore for a short memory film: soft, warm, "
        "unhurried, low dynamic range, nothing percussive or sudden, "
        "designed to sit quietly beneath a spoken voice-over."
    )


def probe_seconds(path: str) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--occasion", default="anniversary", choices=sorted(OCCASIONS))
    args = ap.parse_args()

    occ = OCCASIONS[args.occasion]
    prompt = music_prompt(occ)
    print(f"occasion : {occ.key}  ({occ.music_style}, {occ.tempo:.0f} bpm)")
    print(f"model    : {MINIMAX_MUSIC_MODEL}")
    print(f"prompt   : {prompt}")

    # No storage sink: the bed is a one-off demo asset that gets committed to
    # the repo, so persisting it to B2 as well would spend transactions for a
    # copy nothing reads. Genblaze still seals its own run manifest either way.
    provider = GenblazeMediaProvider(bucket="-")
    provider._bucket = None  # noqa: SLF001 - explicit "no sink" for this one-off

    data = provider.generate(
        model=MINIMAX_MUSIC_MODEL,
        prompt=prompt,
        modality=Modality.AUDIO,
        params={"lyrics": INSTRUMENTAL_LYRICS, **AUDIO_PARAMS},
    )

    os.makedirs(MUSIC_DIR, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    stem = f"{occ.key}-bed"
    mp3 = os.path.join(MUSIC_DIR, f"{stem}.mp3")
    with open(mp3, "wb") as fh:
        fh.write(data)
    seconds = probe_seconds(mp3)

    manifest = {
        "asset": f"video-assets/music/{stem}.mp3",
        "generated": True,
        "licence": "generated for this project; no third-party track is used",
        "provider": "genblaze",
        "platform": "gmicloud",
        "model": MINIMAX_MUSIC_MODEL,
        "prompt": prompt,
        "lyrics": INSTRUMENTAL_LYRICS,
        "params": AUDIO_PARAMS,
        "occasion": {"key": occ.key, "music_style": occ.music_style, "tempo": occ.tempo},
        "sha256": digest,
        "size_bytes": len(data),
        "seconds": round(seconds, 2),
    }
    side = os.path.join(MUSIC_DIR, f"{stem}.json")
    with open(side, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"\nwrote {mp3}  ({len(data)} bytes, {seconds:.2f}s)")
    print(f"sha256 {digest}")
    print(f"wrote {side}")
    gb = provider.last_manifest
    if gb is not None:
        print(f"genblaze manifest sealed: {type(gb).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
