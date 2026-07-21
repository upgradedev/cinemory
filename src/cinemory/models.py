"""Domain models for a Cinemory reel job.

A *reel* is built from ordered *chapters* (a scene, backed by one or more
photos) connected by optional *bridges* (first-last-frame transitions). Each
generative step produces an :class:`Asset` with a real content hash.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Modality(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


@dataclass(frozen=True)
class Photo:
    """A single input photo (synthetic in the reference pipeline)."""

    filename: str
    data: bytes


@dataclass
class Chapter:
    """One scene of the reel."""

    id: str
    label: str
    prompt: str
    photos: list[Photo] = field(default_factory=list)


@dataclass
class Bridge:
    """A first-last-frame transition between two chapters."""

    from_chapter: str
    to_chapter: str
    prompt: str


@dataclass
class ReelSpec:
    """The full description of a reel to generate."""

    name: str
    chapters: list[Chapter] = field(default_factory=list)
    bridges: list[Bridge] = field(default_factory=list)
    music_filename: str | None = None
    aspect_ratio: str = "16:9"
    #: Selected occasion preset key (see ``cinemory.occasions``).
    occasion: str = "anniversary"

    def photo_count(self) -> int:
        return sum(len(c.photos) for c in self.chapters)


@dataclass
class Asset:
    """A generated media artifact with verifiable provenance."""

    modality: Modality
    sha256: str
    size_bytes: int
    url: str | None = None  # durable B2 URL once stored
    filename: str | None = None


@dataclass
class StepRecord:
    """Provenance of a single generative step."""

    provider: str
    model: str
    prompt: str
    modality: Modality
    params: dict
    started_at: str
    finished_at: str
    asset: Asset


@dataclass
class ReelResult:
    """The output of a completed job."""

    reel_name: str
    reel_asset: Asset
    steps: list[StepRecord]
    occasion: str = "anniversary"
    #: The occasion's full creative direction (music/pacing/title/transition),
    #: sealed into the manifest so the reel's styling is part of provenance.
    occasion_style: dict = field(default_factory=dict)
    manifest_uri: str | None = None
    manifest_hash: str | None = None
