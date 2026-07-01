"""Real ffmpeg stitch path — exercised only when ffmpeg is installed.

Skipped (not failed) otherwise, so offline CI without ffmpeg stays green while
the real cinematic path is still verified wherever ffmpeg is present (it is
pre-installed on GitHub's ubuntu-latest runners).
"""
import subprocess

import pytest

from cinemory.stitch import FfmpegStitcher

pytestmark = pytest.mark.skipif(not FfmpegStitcher.available(), reason="ffmpeg not installed")


def _tiny_mp4(seconds: float, color: str) -> bytes:
    import tempfile
    from pathlib import Path

    p = Path(tempfile.mkstemp(suffix=".mp4")[1])
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=128x72:d={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)],
        check=True, capture_output=True,
    )
    return p.read_bytes()


def test_ffmpeg_stitch_produces_playable_mp4(tmp_path):
    clips = [_tiny_mp4(0.5, "red"), _tiny_mp4(0.5, "blue")]
    out = FfmpegStitcher().stitch(clips)
    assert len(out) > 0
    reel = tmp_path / "reel.mp4"
    reel.write_bytes(out)
    # ffprobe confirms the output is a valid video container.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(reel)],
        capture_output=True, text=True,
    )
    assert probe.returncode == 0
    assert float(probe.stdout.strip()) > 0
