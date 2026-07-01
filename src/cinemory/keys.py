"""Content-addressed key strategies for the object store (B2).

HIERARCHICAL mirrors Genblaze's ``KeyStrategy.HIERARCHICAL``: a readable,
collision-free layout ``<reel>/<kind>/<sha2>/<name>`` that dedupes identical
assets by content hash.
"""
from __future__ import annotations

from enum import Enum


class KeyStrategy(str, Enum):
    HIERARCHICAL = "hierarchical"
    FLAT = "flat"


def make_key(strategy: KeyStrategy, *, reel: str, kind: str, sha256: str, name: str) -> str:
    if strategy is KeyStrategy.FLAT:
        return f"{sha256}-{name}"
    return f"{reel}/{kind}/{sha256[:2]}/{sha256}/{name}"
