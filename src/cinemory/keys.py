"""Content-addressed key strategies for the object store (B2).

HIERARCHICAL mirrors Genblaze's ``KeyStrategy.HIERARCHICAL``: a readable,
collision-free layout ``<reel>/<kind>/<sha2>/<name>`` that dedupes identical
assets by content hash.

Security note: the ``reel`` and ``name`` segments originate from user input (the
reel name and the uploaded filename), so both are sanitised into a single safe
path label before they are placed in a storage key. The content anchor (the
SHA-256) is always machine-derived from the asset bytes — never attacker
controlled — so identity stays content-addressed even for a hostile filename.
"""
from __future__ import annotations

import re
from enum import Enum

# Anything outside this conservative label charset is collapsed to ``_``.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


class KeyStrategy(str, Enum):
    HIERARCHICAL = "hierarchical"
    FLAT = "flat"


def safe_component(value: str) -> str:
    """Reduce user-supplied text to a single safe path label.

    Neutralises path traversal and key injection: takes the final path segment
    (so ``../../etc/passwd`` becomes ``passwd``), replaces every character
    outside ``[A-Za-z0-9._-]`` (path separators, NUL, newlines, control chars)
    with ``_``, and strips leading dots (so a bare ``..`` cannot survive). The
    result never contains ``/``, ``\\``, ``..`` as a whole segment, NUL, or a
    leading dot, and is never empty.
    """
    tail = re.split(r"[\\/]", value)[-1]
    cleaned = _UNSAFE.sub("_", tail).lstrip(".")
    return cleaned or "asset"


def make_key(strategy: KeyStrategy, *, reel: str, kind: str, sha256: str, name: str) -> str:
    # ``reel`` and ``name`` are user-controlled → sanitise. ``kind`` and the
    # SHA-256 are machine-derived; sanitising ``kind`` too is cheap defence.
    reel = safe_component(reel)
    kind = safe_component(kind)
    name = safe_component(name)
    if strategy is KeyStrategy.FLAT:
        return f"{sha256}-{name}"
    return f"{reel}/{kind}/{sha256[:2]}/{sha256}/{name}"
