"""Build a :class:`~cinemory.models.ReelSpec` from *real* uploaded photos.

This is the ingest path for the mobile / web client: the caller sends actual
photo bytes (multipart or base64) and this module distributes them into chapters
so the same occasion-aware pipeline that drives the synthetic demo also drives a
real user's memories. It is deliberately separate from :mod:`cinemory.synthetic`
(the only sanctioned *synthetic* photo source) — here the pixels come from the
user, not from Pillow.

No credentials and no network: the resulting spec flows through the exact same
``ReelPipeline`` (offline fakes or live Genblaze/B2), so provenance is sealed for
real either way.
"""
from __future__ import annotations

from .models import Bridge, Chapter, Photo, ReelSpec
from .occasions import get_occasion

#: Guardrails so a bad request is a clean 400, never a 500 or an OOM.
MAX_PHOTOS = 60
MAX_CHAPTERS = 12

#: Magic-byte prefixes for content that must never be accepted as a "photo".
#: These are executables and active/scripted markup — an upload disguised as an
#: image. Assets are already stored with a fixed ``image/*`` content-type, so B2
#: serves them inertly; rejecting the bytes at ingest is defence in depth that
#: keeps such payloads out of the content-addressed store entirely. The list is
#: deliberately tight (a blocklist of dangerous types, not an image allowlist) so
#: legitimate/opaque photo bytes are never falsely rejected.
_DANGEROUS_MAGIC: tuple[bytes, ...] = (
    b"MZ",          # DOS/Windows PE executable
    b"\x7fELF",     # ELF executable
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit
    b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit (LE)
    b"#!",          # script shebang
    b"<?php",       # PHP source
)
#: Case-insensitive markup markers checked against a leading, whitespace-stripped
#: window (active/scriptable HTML masquerading as an image).
_DANGEROUS_MARKUP: tuple[bytes, ...] = (b"<script", b"<!doctype html", b"<html")


class IngestError(ValueError):
    """Raised for an invalid ingest request (maps to HTTP 400)."""


def reject_dangerous_bytes(data: bytes) -> None:
    """Raise :class:`IngestError` if ``data`` is a disguised executable/script.

    Photos are opaque binary, so we only reject content whose leading bytes
    positively identify an executable or active markup payload — never merely
    "not a known image", so ambiguous/opaque bytes still pass.
    """
    if data.startswith(_DANGEROUS_MAGIC):
        raise IngestError("uploaded content is an executable, not a photo")
    head = data[:64].lstrip().lower()
    if head.startswith(_DANGEROUS_MARKUP):
        raise IngestError("uploaded content is active markup, not a photo")


def build_spec_from_photos(
    name: str,
    photos: list[tuple[str, bytes]],
    *,
    occasion: str | None = None,
    chapters: int = 3,
    bridges: bool = False,
) -> ReelSpec:
    """Assemble a :class:`ReelSpec` from ordered ``(filename, bytes)`` photos.

    Photos are distributed across ``chapters`` scenes in upload order (earlier
    chapters absorb the remainder), each scene inheriting the occasion's creative
    direction. Empty chapters (more chapters than photos) are dropped. When
    ``bridges`` is set, a first-last-frame bridge is added between each pair of
    consecutive non-empty chapters.

    Raises:
        IngestError: no photos, a photo with empty bytes, or an out-of-range
            ``chapters`` count.
    """
    if not photos:
        raise IngestError("at least one photo is required")
    if len(photos) > MAX_PHOTOS:
        raise IngestError(f"too many photos (max {MAX_PHOTOS})")
    if any(not data for _, data in photos):
        raise IngestError("one or more photos contained no bytes")
    for _, data in photos:
        reject_dangerous_bytes(data)
    if chapters < 1 or chapters > MAX_CHAPTERS:
        raise IngestError(f"chapters must be between 1 and {MAX_CHAPTERS}")

    occ = get_occasion(occasion)
    labels = occ.scene_labels or ["Chapter"]
    prompts = [
        "gentle camera push-in, warm light, cinematic",
        "slow pan across the scene, soft motion",
        "drifting move at golden hour, lens flare",
        "handheld stroll, bokeh lights",
        "slow fade, calm and reflective",
    ]

    # Distribute photos across chapters as evenly as possible, in order.
    n_chapters = min(chapters, len(photos))
    buckets: list[list[tuple[str, bytes]]] = [[] for _ in range(n_chapters)]
    for i, item in enumerate(photos):
        buckets[i % n_chapters].append(item)

    spec = ReelSpec(
        name=name,
        aspect_ratio=occ.aspect_ratio,
        occasion=occ.key,
        music_filename=f"{occ.key}-{occ.music_style.replace(' ', '-')}",
    )
    for c, bucket in enumerate(buckets):
        chapter_photos = [Photo(filename=fn, data=data) for fn, data in bucket]
        spec.chapters.append(
            Chapter(
                id=f"c{c}",
                label=labels[c % len(labels)],
                prompt=occ.style_prompt(prompts[c % len(prompts)]),
                photos=chapter_photos,
            )
        )

    if bridges:
        for i in range(len(spec.chapters) - 1):
            spec.bridges.append(
                Bridge(
                    from_chapter=spec.chapters[i].id,
                    to_chapter=spec.chapters[i + 1].id,
                    prompt="smooth match-cut transition",
                )
            )

    return spec
