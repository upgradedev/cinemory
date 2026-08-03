#!/usr/bin/env python3
"""CI gate for the committed demo video — A/V + caption-sync + segment order.

Dependency-light on purpose: it needs only ``ffprobe`` and ``ffmpeg`` (on PATH,
or ``FFPROBE``/``FFMPEG``) and the standard library, so it can run as its own
small CI job. It fails the build when the shipped ``demo/cinemory-demo.mp4``
drifts out of spec:

  * the video is missing, over the 180s hard cap, or implausibly short;
  * it is not H.264/yuv420p 1280x720 ~30fps with a single AAC audio track;
  * the one audio track is narration only, or narration under a music bed that
    is mixed too loud (see ``check_music`` below);
  * the beat script, the SRT sidecar and the video disagree on length;
  * the SRT cues do not match the beats one-for-one, in order, by timing and
    by text (so a desynced or re-ordered caption track fails the build); or
  * a beat-referenced asset carries a known-false marker (e.g. a stale
    ``fake-genblaze`` capture) — see ``check_content`` below.

The beat script (``demo/cinemory-demo.beats.json``) is the single source of
truth; ``demo/build-video.py`` regenerates all three artifacts together.

Run:  python scripts/check_video.py        # exit 0 = pass, 1 = fail
"""
from __future__ import annotations

import hashlib
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
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

HARD_CAP_S = 180.0        # never ship a demo at/over three minutes
MIN_S = 60.0              # a real narrated demo is not this short
DUR_TOL_S = 0.5           # container vs. beat-sum slack
CUE_TOL_S = 0.05          # per-cue timing slack vs. the beat windows

# ---------------------------------------------------------------------------
# Music-bed bounds, see ``check_music``. The film carries ONE audio track that
# is narration mixed over a generated music bed, so "how many streams" can no
# longer tell those two apart. These bounds can.
GAP_FLOOR_DB = -50.0      # a window under this is treated as dead air
GAP_MIN_S = 0.30          # ... for at least this long
MAX_DEAD_GAPS = 3         # narration-only measures 44 of them; the mix, 1
LOUDNESS_TOL_LU = 1.0     # mixed film vs. the narration it was built from

# ---------------------------------------------------------------------------
# Content-drift guard — see ``check_content`` for what this does and does not
# catch. Text-decodable assets (.txt/.json/.md/.srt/.html) are scanned for
# these substrings (case-insensitive). Extend when a new known-false marker
# is discovered; keep the list small and specific to avoid false positives on
# a legitimately-labelled offline/degrade capture.
FORBIDDEN_TEXT_MARKERS = ["fake-genblaze"]

# Binary assets (images, video) cannot be cheaply content-scanned without
# OCR, which is exactly the wrong tool for stylised low-contrast text and
# would trade a real gap for a false sense of safety. Instead, the exact
# content hash of every asset ever found to embed a false marker is
# denylisted, so THIS specific bad content can never be shipped again even
# if a filename is reused or a git revert brings the old bytes back.
#   6dea54d3... = old demo/video-assets/cards/cinemory-03-live-proof.png
#                 (showed a mocked "/health" with "provider":"fake-genblaze")
#   105469db... = old demo/video-assets/cards/cinemory-05-provenance.png
#                 (showed a mocked manifest with "provider":"fake-genblaze")
FORBIDDEN_ASSET_SHA256 = {
    "6dea54d3077bfe00b73f42881c016a009084fb0feb94fb96f450c9bdf8ebda94",
    "105469db12041b3a3dc44dae0066e8e702b8f69cab4513e468b21b88995e6a68",
}
TEXT_ASSET_SUFFIXES = {".txt", ".json", ".md", ".srt", ".html", ".htm"}

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


def ffmpeg_filter_log(path: Path, afilter: str) -> str:
    """Run one audio filter over ``path`` to null and return what it logged."""
    out = subprocess.run(
        [FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", afilter, "-f", "null", os.devnull],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path.name}: {out.stderr.strip()[-300:]}")
    return out.stderr + out.stdout


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


def check_content(c: Checks, beats: list[dict]) -> None:
    """Fail the build if a beat-referenced asset carries a known-false marker.

    This is the guard against the exact class of drift that shipped
    ``"provider": "fake-genblaze"`` in two gallery cards: a stale capture,
    made honest when it was taken, that went false later (the account got
    funded, the provider changed) with nothing to catch it until a human
    happened to look. Every asset every beat points at is resolved here —
    the beat script is the single source of truth for what ships in the
    video, so nothing unreferenced needs checking and nothing referenced is
    skipped.

    What this catches:
      * a TEXT-decodable asset (.txt/.json/.md/.srt/.html) whose content
        contains one of ``FORBIDDEN_TEXT_MARKERS`` (case-insensitive) — a
        real, cheap content check, no approximation;
      * a BINARY asset (image/video) whose exact bytes match a sha256 in
        ``FORBIDDEN_ASSET_SHA256`` — catches the exact bad content this
        guard was written for reappearing (a revert, a filename reused for
        old bytes, a copy-paste from an old branch).

    What this does NOT catch: a brand-new binary image that visually shows
    a false marker in its pixels but was never denylisted. Doing that
    generally needs OCR, which is unreliable on small, stylised, low-contrast
    rendered text — a false PASS from a flaky OCR match would be worse than
    this narrower, deterministic check. A new false visual still needs a
    human (or a design-time review) to catch it once and add its hash here;
    this guard's job is to make sure that specific mistake can never ship
    silently a second time.
    """
    print("content:")
    seen: set[Path] = set()
    for beat in beats:
        for rel in beat["assets"]:
            path = DEMO / rel
            if path in seen or not path.exists():
                continue  # existence already checked above; do not double-report
            seen.add(path)
            label = str(path.relative_to(REPO))
            if path.suffix.lower() in TEXT_ASSET_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                hit = next((m for m in FORBIDDEN_TEXT_MARKERS if m.lower() in text), None)
                c.ok(hit is None, f"no forbidden marker in {label}",
                     f"found {hit!r}" if hit else "text scanned")
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                c.ok(digest not in FORBIDDEN_ASSET_SHA256,
                     f"{label} not on the known-false denylist",
                     "binary — identity-checked only, see check_content docstring")


def check_music(c: Checks, mp4: Path, music: dict) -> None:
    """Fail the build if the music bed is missing, swapped, or mixed too loud.

    The bed is generated, not licensed, so it is recorded in the beat script
    with its provider, model and prompt exactly like every other generated
    asset, and pinned here by content hash.

    The mix is a single AAC track: narration and music are summed, not carried
    as separate streams. So ``len(astreams) == 1`` above still catches an
    unexpected stream, but it can no longer tell narration-only from
    narration-plus-music. These two bounds do, and they are two-sided on
    purpose. A one-sided "not silent" check would happily pass a mix that
    drowns the voice.

      * FLOOR (the bed is actually there). The narration track is built by
        padding each beat with digital silence, so a narration-only film has
        long stretches of true dead air between lines: 44 windows at or under
        -50 dBFS for 0.30s or more, measured on the pre-music cut. With the bed
        under it, that count collapses to 1 (the closing fade). If someone
        rebuilds the film without the music step, the count jumps back and this
        fails.

      * CEILING (the voice still wins). The bed is mixed ``duck_lu`` below the
        narration by EBU R128 integrated loudness, which is far enough down
        that summing it moves the whole film's integrated loudness by
        hundredths of a LU. So the mixed film has to still measure within
        ``LOUDNESS_TOL_LU`` of the narration it was built from. A bed mixed
        anywhere near the voice would drag that number up and fail here.
    """
    print("music:")
    bed = DEMO / music["asset"]
    c.ok(bed.exists(), "music bed present", music["asset"])
    if bed.exists():
        digest = hashlib.sha256(bed.read_bytes()).hexdigest()
        c.ok(digest == music["sha256"], "music bed matches its recorded hash",
             f"{digest[:16]}...")
    for field in ("provider", "model", "prompt", "licence"):
        c.ok(bool(str(music.get(field, "")).strip()),
             f"music bed records its {field}")

    log = ffmpeg_filter_log(mp4, f"silencedetect=noise={GAP_FLOOR_DB}dB:d={GAP_MIN_S}")
    gaps = log.count("silence_start")
    c.ok(gaps <= MAX_DEAD_GAPS, "quiet gaps carry the music bed, not dead air",
         f"{gaps} gap(s) under {GAP_FLOOR_DB}dB, max {MAX_DEAD_GAPS}")

    log = ffmpeg_filter_log(mp4, "ebur128=framelog=quiet")
    hits = re.findall(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", log, re.MULTILINE)
    if not hits:
        c.ok(False, "film loudness is measurable")
        return
    mixed = float(hits[-1])
    target = float(music["narration_lufs"])
    c.ok(abs(mixed - target) <= LOUDNESS_TOL_LU,
         "narration still dominates the mix",
         f"film {mixed:.1f} LUFS vs narration {target:.1f} LUFS, "
         f"bed ducked {music['duck_lu']} LU")


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

    # ---- music bed (present, pinned, and mixed under the narration) ---------
    check_music(c, mp4, beats_doc["music"])

    # ---- content drift guard (no known-false marker in any shipped asset) ----
    check_content(c, beats)

    return _report(c)


def _report(c: Checks) -> int:
    if c.failures:
        print(f"\nFAILED: {len(c.failures)} check(s) — " + "; ".join(c.failures))
        return 1
    print("\nOK: demo video, beats and captions are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
