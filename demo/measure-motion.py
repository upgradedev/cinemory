#!/usr/bin/env python3
"""Measure how smoothly a rendered beat moves — the judder check, not by eye.

Why this exists
---------------
ffmpeg's ``zoompan`` steps its crop origin in whole pixels of its *input*. On a
slow zoom the origin therefore sits still for several frames and then jumps,
and the picture trembles instead of gliding. It is a real artifact of the
filter, not a subjective impression, so it should be settled with a number.

How it measures
---------------
Extracts N consecutive frames and recovers the sub-pixel translation between
each consecutive pair by phase correlation (FFT cross-power spectrum with a
parabolic peak fit). A gliding move gives a near-constant motion series; the
integer-origin snap gives runs of near-zero followed by a lurch.

Reported:
  * ``dy series``   per-frame vertical motion (the cleanest signal for a centre
    zoom, since the crop origin steps vertically in whole input pixels)
  * ``mean |d|``    average per-frame motion magnitude
  * ``JERK``        stddev of the first difference of the motion series. This is
    the headline: a perfectly linear glide tends to 0, a lurching one is large.
  * ``stall+jump``  frames that barely move and are immediately followed by one
    moving more than twice the mean — the integer-snap signature.

Result that set ``SUPERSAMPLE = 8`` in ``build-video.py`` (3s test render,
39 frame pairs, same source still and same 1.08 zoom):

    supersample   mean |d| px/frame   JERK     stall+jump
    2 (old)       0.602               0.4130   lurches of 0.87-1.04 px
    4             0.101               0.0542   none
    8 (now)       0.030               0.0207   none

Usage:  python demo/measure-motion.py <clip.mp4> [n_frames] [start_seconds]
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover - tool-only dependency
    sys.exit("[STOP] this tool needs numpy and pillow: pip install numpy pillow")

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")


def extract(path: str, n: int, workdir: str, start: float) -> list[np.ndarray]:
    pat = os.path.join(workdir, "f_%03d.png")
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{start}", "-i", path,
                    "-frames:v", str(n), "-f", "image2", pat], check=True)
    frames = []
    for i in range(1, n + 1):
        p = pat % i
        if not os.path.exists(p):
            break
        a = np.asarray(Image.open(p).convert("L"), dtype=np.float64)
        h, w = a.shape
        # Centre region only: away from the static burned-in caption band, which
        # would otherwise anchor the correlation and hide the real motion.
        frames.append(a[int(h * 0.10):int(h * 0.66), int(w * 0.15):int(w * 0.85)])
    return frames


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Sub-pixel (dy, dx) translation from ``a`` to ``b`` by phase correlation."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    r = np.fft.rfft2(a * win) * np.conj(np.fft.rfft2(b * win))
    mag = np.abs(r)
    mag[mag == 0] = 1e-12
    corr = np.fft.irfft2(r / mag, s=a.shape)
    y, x = np.unravel_index(np.argmax(corr), corr.shape)

    def parab(prev: float, cur: float, nxt: float) -> float:
        d = prev - 2 * cur + nxt
        return 0.0 if d == 0 else 0.5 * (prev - nxt) / d

    yb = parab(corr[(y - 1) % corr.shape[0], x], corr[y, x], corr[(y + 1) % corr.shape[0], x])
    xb = parab(corr[y, (x - 1) % corr.shape[1]], corr[y, x], corr[y, (x + 1) % corr.shape[1]])
    dy = (y + yb) - (corr.shape[0] if y > corr.shape[0] // 2 else 0)
    dx = (x + xb) - (corr.shape[1] if x > corr.shape[1] // 2 else 0)
    return dy, dx


def main() -> int:
    if len(sys.argv) < 2:
        return int(bool(sys.stderr.write(__doc__.rsplit("Usage:", 1)[-1].strip() + "\n")))
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    start = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

    with tempfile.TemporaryDirectory() as wd:
        frames = extract(path, n, wd, start)
        if len(frames) < 3:
            print(f"[STOP] only {len(frames)} frames extracted from {path}")
            return 1
        pairs = [phase_shift(frames[i], frames[i + 1]) for i in range(len(frames) - 1)]

    dys = np.array([p[0] for p in pairs])
    mag = np.hypot(dys, np.array([p[1] for p in pairs]))
    mean = float(np.mean(np.abs(mag)))
    jerk = float(np.std(np.diff(mag)))
    stalls = sum(1 for i in range(len(mag) - 1)
                 if abs(mag[i]) < 0.02 and abs(mag[i + 1]) > max(2 * mean, 0.05))

    print(f"file      : {os.path.basename(path)}")
    print(f"frames    : {len(frames)}  pairs={len(mag)}  from t={start}s")
    print("dy series : " + " ".join(f"{v:+.3f}" for v in dys[:24]))
    print("|d| series: " + " ".join(f"{v:.3f}" for v in mag[:24]))
    print(f"mean |d|  : {mean:.4f} px/frame")
    print(f"JERK      : {jerk:.4f}   (stddev of per-frame change; lower = smoother)")
    print(f"stall+jump: {stalls}   (integer-snap signature; 0 = none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
