"""Adapter selection.

``CINEMORY_MODE=offline`` (default) wires the fakes so the app runs with no
credentials — used by CI and local demos. ``CINEMORY_MODE=live`` wires the real
Genblaze + B2 adapters (requires credentials).
"""
from __future__ import annotations

import os

from .adapters import FakeMediaProvider, FakeStorage
from .ports import MediaProvider, StorageBackend
from .stitch import FakeStitcher, FfmpegStitcher


def mode() -> str:
    return os.environ.get("CINEMORY_MODE", "offline").lower()


def build_provider() -> MediaProvider:
    if mode() == "live":
        from .adapters.genblaze_provider import GenblazeMediaProvider

        return GenblazeMediaProvider()
    return FakeMediaProvider()


def build_storage() -> StorageBackend:
    if mode() == "live":
        from .adapters.b2_storage import B2Storage

        return B2Storage()
    return FakeStorage()


def build_stitcher():
    # Real ffmpeg grade when available and requested; deterministic fake otherwise.
    if os.environ.get("CINEMORY_STITCH") == "ffmpeg" and FfmpegStitcher.available():
        return FfmpegStitcher()
    return FakeStitcher()
