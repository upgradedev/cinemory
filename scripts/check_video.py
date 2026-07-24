#!/usr/bin/env python3
"""CI gate for the committed demo video — A/V + caption-sync + segment order.

Dependency-light on purpose: it needs only ``ffprobe`` (on PATH, or ``FFPROBE``)
and the standard library, so it can run as its own small CI job. It fails the
build when the shipped ``demo/cinemory-demo.mp4`` drifts out of spec:

  * the video is missing, over the 180s hard cap, or implausibly short;
  * it is not H.264/yuv420p 1280x720 ~30fps with a single AAC audio track;
  * the beat script, the SRT sidecar and the video disagree on length; or
  * the SRT cues do not match the beats one-for-one, in order, by timing and
    by text (so a desynced or re-ordered caption track fails the build).

The beat script (``demo/cinemory-demo.beats.json``) is the single source of
truth; ``demo/build-video.py`` regenerates all three artifacts together.

Run:  python scripts/check_video.py        # exit 0 = pass, 1 = fail
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "demo"
BEATS_JSON = DEMO / "cinemory-demo.beats.json"
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

HARD_CAP_S = 180.0        # never ship a demo at/over three minutes
MIN_S = 60.0              # a real narrated demo is not this short
DUR_TOL_S = 0.5           # container vs. beat-sum slack
CUE_TOL_S = 0.05          # per-cue timing slack vs. the beat windows

_TS = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")


def norm(text: str) -> str:
    return " ".join(text.split())


def ts_to_seconds(stamp: str) -> float:
    m = _TS.match(stamp.strip())
    if not m:
        raise ValueError(f"bad SRT timestamp: {stamp!r}")
    h, mm, ss, ms = (int(g) for g in m.groups())
    return h * 3600 + mm * 60 + ss + ms / 1000.0


def ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


def parse_srt(text: str) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) < 2 or "-->" not in lines[1]:
            continue
        start_s, end_s = (p.strip() for p in lines[1].split("-->"))
        cues.append({
            "index": int(lines[0].strip()),
            "start": ts_to_seconds(start_s),
            "end": ts_to_seconds(end_s),
            "text": norm(" ".join(lines[2:])),
        })
    return cues


class Checks:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, cond: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if cond else "FAIL"
        print(f"  [{mark}] {label}" + (f"  ({detail})" if detail else ""))
        if not cond:
            self.failures.append(label)


def main() -> int:
    if not BEATS_JSON.exists():
        print(f"[STOP] missing beat script: {BEATS_JSON}")
        return 1
    beats_doc = json.loads(BEATS_JSON.read_text(encoding="utf-8"))
    beats = beats_doc["beats"]
    fps = int(beats_doc["fps"])
    total = float(beats_doc["total_seconds"])
    mp4 = DEMO / beats_doc["video"]
    srt = DEMO / beats_doc["srt"]

    c = Checks()
    print(f"demo video gate — {mp4.name} · {len(beats)} beats · {total:.2f}s")

    # ---- media ---------------------------------------------------------------
    print("media:")
    c.ok(mp4.exists(), "video file present", str(mp4.relative_to(REPO)))
    if not mp4.exists():
        return _report(c)
    probe = ffprobe_json(mp4)
    duration = float(probe["format"]["duration"])
    vstreams = [s for s in probe["streams"] if s.get("codec_type") == "video"]
    astreams = [s for s in probe["streams"] if s.get("codec_type") == "audio"]
    c.ok(duration < HARD_CAP_S, "under 180s hard cap", f"{duration:.2f}s")
    c.ok(duration > MIN_S, "not implausibly short", f"{duration:.2f}s")
    c.ok(abs(duration - total) <= DUR_TOL_S, "video length matches beat sum",
         f"video {duration:.2f}s vs beats {total:.2f}s")
    c.ok(len(vstreams) == 1, "exactly one video stream", str(len(vstreams)))
    c.ok(len(astreams) == 1, "exactly one audio stream", str(len(astreams)))
    if vstreams:
        v = vstreams[0]
        num, den = (v.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
        vfps = float(num) / float(den) if float(den) else 0.0
        c.ok(v.get("codec_name") == "h264", "video is H.264", str(v.get("codec_name")))
        c.ok(v.get("pix_fmt") == "yuv420p", "pixel format yuv420p", str(v.get("pix_fmt")))
        c.ok((v.get("width"), v.get("height")) == (beats_doc["width"], beats_doc["height"]),
             "resolution matches", f'{v.get("width")}x{v.get("height")}')
        c.ok(abs(vfps - fps) < 0.5, "frame rate matches", f"{vfps:.2f}fps")
    if astreams:
        c.ok(astreams[0].get("codec_name") == "aac", "audio is AAC",
             str(astreams[0].get("codec_name")))

    # ---- beat windows --------------------------------------------------------
    print("beats:")
    c.ok(len(beats) >= 5, "has a real beat list", str(len(beats)))
    indices_ok = [b["index"] for b in beats] == list(range(1, len(beats) + 1))
    c.ok(indices_ok, "beat indices are 1..N in order")
    for a in (DEMO / rel for b in beats for rel in b["assets"]):
        c.ok(a.exists(), "beat asset present", str(a.relative_to(REPO)))
    windows_ok, t = True, 0.0
    for b in beats:
        if abs(b["start"] - t) > CUE_TOL_S or abs(b["end"] - (b["start"] + b["dur"])) > CUE_TOL_S:
            windows_ok = False
        t = b["end"]
    c.ok(windows_ok, "beat windows are contiguous and non-overlapping")
    c.ok(abs(t - total) <= CUE_TOL_S, "beat windows sum to total", f"{t:.2f}s")

    # ---- SRT vs beats (count, order, timing, text) ---------------------------
    print("captions:")
    c.ok(srt.exists(), "SRT sidecar present", str(srt.relative_to(REPO)))
    if srt.exists():
        cues = parse_srt(srt.read_text(encoding="utf-8"))
        c.ok(len(cues) == len(beats), "one SRT cue per beat",
             f"{len(cues)} cues vs {len(beats)} beats")
        c.ok(bool(cues) and abs(cues[0]["start"]) <= CUE_TOL_S, "first cue starts at 0")
        c.ok(bool(cues) and abs(cues[-1]["end"] - duration) <= DUR_TOL_S,
             "last cue ends with the video", f"{cues[-1]['end']:.2f}s" if cues else "no cues")
        aligned = True
        for i, (cue, beat) in enumerate(zip(cues, beats, strict=False)):
            if (cue["index"] != beat["index"]
                    or abs(cue["start"] - beat["start"]) > CUE_TOL_S
                    or abs(cue["end"] - beat["end"]) > CUE_TOL_S
                    or cue["text"] != norm(beat["narration"])):
                aligned = False
                print(f"    - cue {i + 1} disagrees with beat {beat['id']}")
        c.ok(aligned, "every cue matches its beat (order, timing, text)")

    return _report(c)


def _report(c: Checks) -> int:
    if c.failures:
        print(f"\nFAILED: {len(c.failures)} check(s) — " + "; ".join(c.failures))
        return 1
    print("\nOK: demo video, beats and captions are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
