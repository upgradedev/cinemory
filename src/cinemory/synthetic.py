"""Synthetic demo photo generation — the PII-safe input source.

Photos are drawn programmatically (gradients + shapes) with Pillow, so the demo
and the public repo contain ZERO real personal media. Deterministic per seed for
reproducible tests. This is the ONLY sanctioned source of input photos for the
reference pipeline.
"""
from __future__ import annotations

import io
import random

from .models import Chapter, Photo, ReelSpec

# Fixed palette so output is deterministic and pleasant.
_PALETTES = [
    [(28, 42, 84), (86, 132, 214), (222, 236, 255)],
    [(84, 28, 42), (214, 96, 88), (255, 236, 222)],
    [(28, 84, 52), (96, 200, 132), (232, 255, 236)],
    [(72, 52, 96), (168, 120, 214), (244, 236, 255)],
]


def synth_photo(filename: str, *, seed: int, size: tuple[int, int] = (1024, 576)) -> Photo:
    """Generate one deterministic synthetic photo as PNG bytes.

    The default is 16:9 at **1024×576** — deliberately above GMI Kling's
    300px minimum side. The previous 512×288 default failed live I2V submits
    with ``Image pixel is invalid`` (288 < 300), silently degrading the
    synthetic-JSON path (``POST /reels``); 1024×576 is proven working live
    (2026-07-22). Keep any override's shortest side >= 300px for live runs.
    """
    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    w, h = size
    palette = _PALETTES[seed % len(_PALETTES)]
    top, mid, bottom = palette

    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        if t < 0.5:
            a, b, f = top, mid, t / 0.5
        else:
            a, b, f = mid, bottom, (t - 0.5) / 0.5
        row = tuple(int(a[i] + (b[i] - a[i]) * f) for i in range(3))
        for x in range(w):
            px[x, y] = row

    draw = ImageDraw.Draw(img, "RGBA")
    for _ in range(rng.randint(3, 6)):
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        r = rng.randint(20, 70)
        col = (rng.randint(180, 255), rng.randint(180, 255), rng.randint(180, 255), 70)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Photo(filename=filename, data=buf.getvalue())


def synth_reel_spec(
    name: str = "demo-reel",
    *,
    chapters: int = 3,
    per_chapter: int = 2,
    occasion: str | None = None,
) -> ReelSpec:
    """Build a full synthetic ReelSpec ready for the pipeline.

    ``occasion`` selects a preset (see :mod:`cinemory.occasions`) that adjusts
    scene labels, prompt direction, music mood and aspect ratio. Defaults to the
    anniversary preset — Cinemory's origin — when omitted.
    """
    from .occasions import get_occasion

    occ = get_occasion(occasion)
    default_labels = ["Arrival", "The Coast", "Golden Hour", "Night Market", "Farewell"]
    labels = occ.scene_labels or default_labels
    prompts = [
        "gentle camera push-in, warm morning light, cinematic",
        "slow pan across a sunlit shoreline, soft waves",
        "drifting drone shot at golden hour, lens flare",
        "handheld stroll through glowing stalls, bokeh lights",
        "slow fade under a starlit sky, calm and reflective",
    ]
    spec = ReelSpec(
        name=name,
        aspect_ratio=occ.aspect_ratio,
        occasion=occ.key,
        music_filename=f"{occ.key}-{occ.music_style.replace(' ', '-')}",
    )
    seed = 0
    for c in range(chapters):
        photos = [
            synth_photo(f"c{c}_p{p}.png", seed=(seed := seed + 1))
            for p in range(per_chapter)
        ]
        spec.chapters.append(
            Chapter(id=f"c{c}", label=labels[c % len(labels)],
                    prompt=occ.style_prompt(prompts[c % len(prompts)]), photos=photos)
        )
    return spec
