#!/usr/bin/env python3
"""Cut the per-beat live-app clips out of one screen-capture take.

``demo/capture-live.py`` records the whole journey to ``demo/.capture/`` (raw,
git-ignored, tens of MB). This turns that single take into the small H.264
clips the video is actually built from, one per live beat, committed under
``demo/video-assets/footage/``.

Each clip is cut from the mark where its phase begins and is exactly as long as
that beat's narration plus a little headroom. Beat durations are not guessed:
this imports ``build-video.py`` and runs its real audio pass to measure them.
The ElevenLabs responses are cached by a hash of (text + voice + model), so
this costs nothing beyond the first synthesis of each line.

The five clips are contiguous spans of ONE take, in order, so the finished
video shows the product running continuously. The only thing skipped is the
multi-minute wait while the live model renders, which beat 04 states out loud.

Usage:
  python demo/cut-footage.py [--take demo/.capture] [--headroom 0.5]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys

DEMO = os.path.dirname(os.path.abspath(__file__))
FOOTAGE = os.path.join(DEMO, "video-assets", "footage")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

#: beat id -> (mark the cut starts from, extra seconds to let the step settle)
CUTS: dict[str, tuple[str, float]] = {
    "02-photos": ("landing", 0.0),
    "03-occasion": ("step2_open", 0.0),
    "04-rolling": ("generate_clicked", 1.0),
    "05-reel": ("reel_playing", 0.0),
    # Start late enough that the green "Verified" badge and the 9/9 server
    # receipt are on screen for the last several seconds rather than flashing
    # up as the beat ends: the browser recomputation takes ~9s against the live
    # service, and the narration's payoff ("the seal reads Verified") lands at
    # the end of the line.
    "06-verify": ("provenance_open", 2.3),
}


def load_build_video():
    spec = importlib.util.spec_from_file_location("bv", os.path.join(DEMO, "build-video.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bv"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", default=os.path.join(DEMO, ".capture"))
    ap.add_argument("--headroom", type=float, default=0.5,
                    help="extra seconds kept past each beat's length")
    args = ap.parse_args()

    webm = os.path.join(args.take, "journey.webm")
    marks_path = os.path.join(args.take, "journey.marks.json")
    for p in (webm, marks_path):
        if not os.path.exists(p):
            raise SystemExit(f"[STOP] missing {p} — run demo/capture-live.py first")
    doc = json.loads(open(marks_path, encoding="utf-8").read())
    at = {m["name"]: m["t"] for m in doc["marks"]}

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("[STOP] ELEVENLABS_API_KEY is not set — needed to measure "
                         "each beat's real length before cutting to it.")
    bv = load_build_video()
    os.makedirs(bv.WORK, exist_ok=True)
    os.makedirs(bv.CACHE, exist_ok=True)
    os.makedirs(FOOTAGE, exist_ok=True)
    print("[cut] measuring beat lengths from the real narration…")
    _voice, durations = bv.build_audio(bv.BEATS, key)

    total_bytes = 0
    for beat, dur in zip(bv.BEATS, durations, strict=True):
        if not beat.live:
            continue
        if beat.id not in CUTS:
            raise SystemExit(f"[STOP] no cut point defined for live beat {beat.id!r}")
        mark, settle = CUTS[beat.id]
        if mark not in at:
            raise SystemExit(f"[STOP] take has no mark {mark!r} for beat {beat.id}")
        start = at[mark] + settle
        length = dur + args.headroom
        out = os.path.join(FOOTAGE, f"{beat.id}.mp4")
        # Constant-rate 30fps at the delivery resolution. CRF 23 is plenty for
        # flat UI screen content and keeps the committed clips small.
        cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", webm,
               "-t", f"{length:.3f}",
               "-vf", f"fps={bv.FPS},scale={bv.W}:{bv.H}:flags=lanczos,format=yuv420p",
               "-an", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            sys.stderr.write(r.stderr.decode(errors="replace")[-1200:] + "\n")
            raise SystemExit(f"[STOP] ffmpeg failed cutting {beat.id}")
        size = os.path.getsize(out)
        total_bytes += size
        got = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", out],
            capture_output=True, text=True).stdout.strip() or 0.0)
        flag = "" if got >= dur - 0.05 else "   <-- SHORT, will freeze on its last frame"
        print(f"[cut] {beat.id:<12} from {mark:<18} t={start:7.2f}s  "
              f"need={dur:5.2f}s got={got:5.2f}s  {size // 1024:5d} KB{flag}")

    print(f"[ok] {FOOTAGE}  ({total_bytes // 1024} KB total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
