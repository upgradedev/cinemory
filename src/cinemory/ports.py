"""Ports (protocols) that decouple orchestration from concrete providers.

The real adapters wrap Genblaze (generation) and Backblaze B2 / S3 (storage).
The fake adapters implement the same protocols with no network, so the whole
pipeline — including real SHA-256 provenance — runs offline in CI.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Modality


@runtime_checkable
class MediaProvider(Protocol):
    """A generative-media backend (video / image / audio).

    The real implementation delegates to a Genblaze provider adapter; the fake
    returns deterministic bytes so orchestration and hashing are exercised
    without any API calls.
    """

    name: str

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        modality: Modality,
        inputs: list[bytes] | None = None,
        params: dict | None = None,
    ) -> bytes:
        """Return the raw bytes of the generated asset."""
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """An object store (Backblaze B2 / any S3-compatible store)."""

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        """Store ``data`` under ``key``; return a durable URL."""
        ...

    def get(self, key: str) -> bytes:
        """Fetch the bytes stored under ``key``."""
        ...

    def exists(self, key: str) -> bool:
        ...


@runtime_checkable
class Stitcher(Protocol):
    """Assembles ordered clip bytes into a single reel artifact."""

    name: str

    def stitch(self, clips: list[bytes]) -> bytes:
        ...
