#!/usr/bin/env python3
"""Lay the generated music bed under the finished demo video.

Run at the very end of ``demo/build-video.py``, after the per-beat segments have
been concatenated. It never touches the picture: the video stream is stream
copied, so the beat windows, the caption timings and every footage cut survive
byte for byte.

Two things make this more than an ``amix`` one-liner:

1. **The bed is shorter than the film.** ``minimax-music-2.5`` gives no duration
   control, so the generated bed is 90.26s against a 169.74s film. It is looped
   by crossfading the bed into a second copy of itself with a constant power
   (``qsin``) curve, which on a sustained strings pad puts the seam below the
   level where a listener can point at it. The loop is then trimmed to the exact
   video length and given a short fade in and fade out.

2. **Narration stays dominant.** Both tracks are measured with EBU R128
   integrated loudness, and the bed is attenuated so it sits exactly
   ``DUCK_LU`` below the voice. The mix uses ``normalize=0`` so ``amix`` cannot
   quietly halve both inputs and undo the measurement.

Usage:  python demo/mix-music.py IN.mp4 BED.mp3 OUT.mp4
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

DUCK_LU = 20.1        # how far under the narration the bed sits, EBU R128
XFADE_S = 4.0         # loop seam length, constant power
FADE_IN_S = 2.0       # bed eases in under the opening line
FADE_OUT_S = 3.0      # and out under the closing card

_I = re.compile(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", re.MULTILINE)


def run(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"[STOP] {cmd[0]} failed:\n{proc.stderr.strip()[-1500:]}")
    return proc.stderr + proc.stdout


def duration(path: str) -> float:
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path])
    return float(out.strip().splitlines()[-1])


def loudness(path: str) -> float:
    """Integrated loudness in LUFS, EBU R128 gated (silence padding excluded)."""
    out = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
               "-af", "ebur128=framelog=quiet", "-f", "null", os.devnull])
    hits = _I.findall(out)
    if not hits:
        raise SystemExit(f"[STOP] could not measure loudness of {path}")
    return float(hits[-1])


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    src_mp4, bed_mp3, out_mp4 = argv[1:]

    video_s = duration(src_mp4)
    bed_s = duration(bed_mp3)
    print(f"[mix] film {video_s:.3f}s · bed {bed_s:.3f}s · duck {DUCK_LU} LU")

    copies = 1
    while bed_s + (copies - 1) * (bed_s - XFADE_S) < video_s:
        copies += 1
        if copies > 12:
            raise SystemExit("[STOP] bed is too short to loop sensibly")
    print(f"[mix] looping the bed {copies}x with a {XFADE_S}s constant power seam")

    work = tempfile.mkdtemp(prefix="cinemory-mix-")
    try:
        narration = os.path.join(work, "narration.wav")
        run([FFMPEG, "-y", "-v", "error", "-i", src_mp4, "-vn",
             "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", narration])

        # Crossfade N copies of the bed into one another, trim to the film,
        # then ease the result in and out.
        inputs: list[str] = []
        for _ in range(copies):
            inputs += ["-i", bed_mp3]
        chain, prev = [], "0:a"
        for i in range(1, copies):
            label = f"x{i}"
            chain.append(f"[{prev}][{i}:a]acrossfade=d={XFADE_S}:c1=qsin:c2=qsin[{label}]")
            prev = label
        fade_at = max(0.0, video_s - FADE_OUT_S)
        chain.append(
            f"[{prev}]atrim=0:{video_s:.6f},asetpts=N/SR/TB,"
            f"afade=t=in:st=0:d={FADE_IN_S},"
            f"afade=t=out:st={fade_at:.6f}:d={FADE_OUT_S},"
            f"aresample=44100[bed]"
        )
        bed = os.path.join(work, "bed.wav")
        run([FFMPEG, "-y", "-v", "error", *inputs,
             "-filter_complex", ";".join(chain), "-map", "[bed]",
             "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", bed])

        i_nar, i_bed = loudness(narration), loudness(bed)
        gain = (i_nar - DUCK_LU) - i_bed
        print(f"[mix] narration {i_nar:.1f} LUFS · bed {i_bed:.1f} LUFS "
              f"· applying {gain:+.2f} dB")

        ducked = os.path.join(work, "ducked.wav")
        run([FFMPEG, "-y", "-v", "error", "-i", bed, "-af", f"volume={gain:.3f}dB",
             "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", ducked])

        measured = i_nar - loudness(ducked)
        print(f"[mix] measured separation {measured:.2f} LU (target {DUCK_LU})")
        if abs(measured - DUCK_LU) > 0.5:
            raise SystemExit(f"[STOP] narration/bed separation drifted to {measured:.2f} LU")

        tmp_out = os.path.join(work, "out.mp4")
        run([FFMPEG, "-y", "-v", "error", "-i", src_mp4, "-i", narration, "-i", ducked,
             "-filter_complex",
             "[1:a][2:a]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[a]",
             "-map", "0:v:0", "-map", "[a]", "-t", f"{video_s:.6f}",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
             "-movflags", "+faststart", tmp_out])

        got = duration(tmp_out)
        if abs(got - video_s) > 0.1:
            raise SystemExit(f"[STOP] mixed video {got:.3f}s vs source {video_s:.3f}s")
        shutil.move(tmp_out, out_mp4)
        print(f"[ok] {out_mp4}  {got:.3f}s  (video stream copied, picture untouched)")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
