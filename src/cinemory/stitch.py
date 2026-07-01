"""Reel assembly (stitching) — pluggable behind the :class:`Stitcher` port.

``FakeStitcher`` is deterministic and dependency-free (offline CI). It frames
each clip with a length-prefixed header so the assembled reel is reproducible
and its byte content is a pure function of the inputs.

``FfmpegStitcher`` is the real cinematic path (concat + colour grade), exercised
by an integration test that is skipped when ffmpeg is unavailable.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


class FakeStitcher:
    """Deterministic, ffmpeg-free reel assembly for offline runs."""

    name = "fake-stitcher"
    _HEADER = b"MRREEL01"

    def stitch(self, clips: list[bytes]) -> bytes:
        out = bytearray(self._HEADER)
        out += struct.pack(">I", len(clips))
        for clip in clips:
            out += struct.pack(">I", len(clip))
            out += clip
        return bytes(out)


class FfmpegStitcher:
    """Real cinematic stitch: concat clips, then a warm colour grade.

    Grade ported (concept only) from cinemory's worker: warm curves, lifted
    blacks, vignette, unsharp.
    """

    name = "ffmpeg-stitcher"

    @staticmethod
    def available() -> bool:
        return shutil.which("ffmpeg") is not None

    def stitch(self, clips: list[bytes]) -> bytes:
        if not self.available():
            raise RuntimeError("ffmpeg not found on PATH")
        work = Path(tempfile.mkdtemp(prefix="cinemory_"))
        concat = work / "concat.txt"
        paths = []
        for i, clip in enumerate(clips):
            p = work / f"clip_{i:04d}.mp4"
            p.write_bytes(clip)
            paths.append(p)
        concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in paths))

        pass_a = work / "pass_a.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", str(pass_a)],
            check=True, capture_output=True,
        )
        out = work / "reel.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(pass_a), "-vf",
             "curves=r='0/0 0.5/0.55 1/1':g='0/0 0.5/0.52 1/1':b='0/0 0.5/0.45 1/1',"
             "curves=all='0/0.04 1/0.96',vignette=PI/4,unsharp=3:3:0.5:3:3:0",
             "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", str(out)],
            check=True, capture_output=True,
        )
        return out.read_bytes()
