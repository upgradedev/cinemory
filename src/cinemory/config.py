"""Adapter selection.

``CINEMORY_MODE=offline`` (default) wires the fakes so the app runs with no
credentials — used by CI and local demos. ``CINEMORY_MODE=live`` wires the real
Genblaze + B2 adapters (requires credentials).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .adapters import FakeMediaProvider, FakeStorage
from .ports import MediaProvider, StorageBackend
from .stitch import FakeStitcher, FfmpegStitcher


def mode() -> str:
    return os.environ.get("CINEMORY_MODE", "offline").lower()


# ── Backblaze B2 credential resolution ───────────────────────────────────────
# The live path reads B2 config from the environment. Two equally-valid name
# sets are accepted so users who already export Backblaze's own canonical names
# need not edit ``.env`` at all:
#
#   field     legacy (Cinemory)   canonical fallback (Backblaze-native)
#   -------   -----------------   -------------------------------------
#   key_id    B2_KEY_ID           B2_APPLICATION_KEY_ID
#   app_key   B2_APP_KEY          B2_APPLICATION_KEY
#   bucket    B2_BUCKET_NAME      (same)
#   endpoint  B2_ENDPOINT_URL     B2_S3_ENDPOINT
#   region    B2_REGION           (derived from the endpoint host)
#
# Resolution is a pure function with no side effects and is only invoked on the
# live path — the offline default never touches it, so credential-free CI and
# local demos are unaffected.


@dataclass(frozen=True)
class B2Config:
    """Resolved Backblaze B2 settings (any field may be ``None`` if unset)."""

    bucket: str | None
    endpoint_url: str | None
    key_id: str | None
    app_key: str | None
    region: str | None
    key_prefix: str | None


def _first_env(*names: str) -> str | None:
    """First non-empty environment value among ``names`` (precedence = order)."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _normalize_endpoint(url: str | None) -> str | None:
    """Ensure an endpoint has an explicit scheme (default ``https://``)."""
    if not url:
        return url
    if "://" in url:
        return url
    return f"https://{url}"


def _derive_region(endpoint_url: str | None) -> str | None:
    """Extract the region from a Backblaze S3 host.

    ``https://s3.eu-central-003.backblazeb2.com`` -> ``eu-central-003``.
    Returns ``None`` when the host is not a recognisable ``s3.<region>`` B2 host
    (callers then fall back to whatever region the SDK defaults to).
    """
    if not endpoint_url:
        return None
    host = endpoint_url.split("://", 1)[-1].split("/", 1)[0]
    labels = host.split(".")
    if len(labels) >= 4 and labels[0] == "s3" and labels[-2:] == ["backblazeb2", "com"]:
        return labels[1]
    return None


def resolve_b2_config() -> B2Config:
    """Resolve B2 settings from the environment (legacy name, then canonical)."""
    endpoint = _normalize_endpoint(_first_env("B2_ENDPOINT_URL", "B2_S3_ENDPOINT"))
    return B2Config(
        bucket=_first_env("B2_BUCKET_NAME"),
        endpoint_url=endpoint,
        key_id=_first_env("B2_KEY_ID", "B2_APPLICATION_KEY_ID"),
        app_key=_first_env("B2_APP_KEY", "B2_APPLICATION_KEY"),
        region=_first_env("B2_REGION") or _derive_region(endpoint),
        key_prefix=_first_env("B2_KEY_PREFIX", "B2_PREFIX"),
    )


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
