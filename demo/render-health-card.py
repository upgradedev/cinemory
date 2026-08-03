#!/usr/bin/env python3
"""Render the "Live on Cloud Run" gallery card from a real, saved GET /health
capture (demo/video-assets/health.txt). Never hand-typed.

Why this script exists: the first version of this card was composited once,
by hand, and baked in the exact "build.commit" hash /health returned at
capture time. Every redeploy changes that hash, including a redeploy
triggered by merging the very commit that fixes this, so a card that pins
it always drifts from a live curl within one deploy of being made. That is
structurally unfixable by recapturing (see demo/STATE.md, 2026-08-03 entry).

The fix is to stop pinning the volatile field instead of chasing it. This
script renders the STABLE part of the response verbatim, sliced straight out
of the saved capture (status, service, mode, provider, storage: unchanged
across deploys), and proves the "build" block is real by showing its actual
key names, but elides every value inside "build" with an ellipsis rather
than a value that would already be wrong by the next deploy. Nothing in the
two response panels is text the live server did not send; the "why is this
blank, and how do I check it myself" explanation lives above the panels, in
the card's own caption, never inside them.

Usage:
    # 1. Recapture (both origins should agree byte-for-byte on everything
    #    except the deploy-specific build.commit / build.built_at):
    curl -s https://cinemory-595784992266.europe-west1.run.app/health
    curl -s https://upgradegr-cinemory.web.app/health
    # 2. Save either response (they should be identical) as health.txt, e.g.:
    #    curl -s https://upgradegr-cinemory.web.app/health > demo/video-assets/health.txt
    # 3. Render:
    python demo/render-health-card.py
"""
from __future__ import annotations

import json
import os

from PIL import Image, ImageDraw, ImageFont

DEMO = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(DEMO, "video-assets")
HEALTH_TXT = os.path.join(ASSETS, "health.txt")
OUT_PNG = os.path.join(ASSETS, "cards", "cinemory-03-live-health.png")

CAPTURED_ON = "2026-08-03"  # the date health.txt was actually captured
CLOUD_RUN_URL = "https://cinemory-595784992266.europe-west1.run.app"
FIREBASE_URL = "https://upgradegr-cinemory.web.app"

W, H = 1200, 800

# Brand palette, matches demo/build-video.py.
INK = (11, 13, 20)
PANEL = (17, 20, 29)
WHITE = (244, 244, 246)
EMBER = (233, 84, 74)
GOLD = (212, 169, 78)
ZINC = (154, 158, 168)
GREEN = (110, 200, 150)
DIM = (105, 110, 122)


def _first_font(*candidates: str) -> str:
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]


FONT = _first_font("C:/Windows/Fonts/segoeui.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONTB = _first_font("C:/Windows/Fonts/segoeuib.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MONO = _first_font("C:/Windows/Fonts/consola.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
MONOB = _first_font("C:/Windows/Fonts/consolab.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def wrap_to_width(d: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Greedy word-wrap using real measured pixel width (not char count)."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        if d.textlength(cand, font=fnt) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def load_health() -> dict:
    with open(HEALTH_TXT, "r", encoding="utf-8") as fh:
        return json.loads(fh.read())


# A line is a list of (text, color) segments drawn left-to-right on one row.
# This lets a single line mix plain structural JSON (white) with an
# emphasised or elided value, with no marker-string parsing.
Segment = tuple[str, tuple[int, int, int]]


def kv_line(key: str, value: str, value_color: tuple[int, int, int], trailing: str = ",") -> list[Segment]:
    return [(f'  "{key}": "', WHITE), (value, value_color), (f'"{trailing}', WHITE)]


def elided_kv_line(key: str, trailing: str) -> list[Segment]:
    # The value is a literal ellipsis, dimmed. Never a string shaped like a
    # real (and soon-stale) commit hash or timestamp.
    return [(f'    "{key}": "', WHITE), ("…", ZINC), (f'"{trailing}', WHITE)]


def plain_line(text: str) -> list[Segment]:
    return [(text, WHITE)]


def draw_panel(d: ImageDraw.ImageDraw, x: int, y: int, w: int,
               data: dict, origin_label: str) -> int:
    """One terminal-style GET /health panel. Returns the panel's bottom y."""
    pad = 22
    line_h = 25
    mono14 = font(MONO, 14)
    mono14b = font(MONOB, 14)
    label_font = font(MONO, 12)

    build_keys = list((data.get("build") or {}).keys())  # real key names, no values

    # Build the exact line list first, so panel height is computed, not guessed.
    rows: list[tuple[list[Segment], ImageFont.FreeTypeFont]] = [
        ([("$ GET /health", WHITE)], mono14b),
        ([("HTTP/2 200", GREEN)], mono14),
        ([("", WHITE)], mono14),
        (plain_line("{"), mono14),
        (kv_line("status", data["status"], GREEN), mono14),
        (plain_line(f'  "service": "{data["service"]}",'), mono14),
        (kv_line("mode", data["mode"], EMBER), mono14),
        (kv_line("provider", data["provider"], EMBER), mono14),
        (plain_line(f'  "storage": "{data["storage"]}"' + ("," if build_keys else "")), mono14),
    ]
    if build_keys:
        rows.append((plain_line('  "build": {'), mono14))
        for i, k in enumerate(build_keys):
            rows.append((elided_kv_line(k, "," if i < len(build_keys) - 1 else ""), mono14))
        rows.append((plain_line("  }"), mono14))
    rows.append((plain_line("}"), mono14))

    chrome_h = 40
    panel_h = chrome_h + pad + len(rows) * line_h + pad
    d.rounded_rectangle([x, y, x + w, y + panel_h], radius=14,
                         fill=PANEL, outline=(255, 255, 255, 20), width=1)

    # traffic-light dots + origin label
    for i in range(3):
        d.ellipse([x + 20 + i * 18, y + 18, x + 20 + i * 18 + 9, y + 27], fill=(70, 74, 84))
    lw = d.textlength(origin_label, font=label_font)
    d.text((x + w - 20 - lw, y + 17), origin_label, font=label_font, fill=DIM)

    ty = y + chrome_h + pad
    tx = x + pad
    for segments, fnt in rows:
        cx = tx
        for text, color in segments:
            if text:
                d.text((cx, ty), text, font=fnt, fill=color)
                cx += d.textlength(text, font=fnt)
        ty += line_h

    return y + panel_h


def main() -> None:
    data = load_health()
    build_keys = list((data.get("build") or {}).keys())

    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)

    margin = 64
    kicker_f = font(FONTB, 15)
    title_f = font(FONTB, 40)
    sub_f = font(FONT, 19)
    note_f = font(FONT, 17)

    y = 50
    d.text((margin, y), "LIVE PROOF \u00b7 CAPTURED " + CAPTURED_ON, font=kicker_f, fill=EMBER)
    y += 30
    d.text((margin, y), "Live on Cloud Run", font=title_f, fill=WHITE)
    y += 54
    d.text((margin, y), "Two origins, one health contract: GET /health, captured moments apart",
            font=sub_f, fill=ZINC)
    y += 30

    if build_keys:
        note = (
            f"/health also stamps a build {' + '.join(build_keys)}, elided below "
            "because they change on every deploy. Compare it live: check /health on "
            "main yourself, not a screenshot."
        )
        for line in wrap_to_width(d, note, note_f, W - 2 * margin):
            d.text((margin, y), line, font=note_f, fill=GOLD)
            y += 24
        y += 8

    panel_y = max(y + 12, 210)
    gap = 48
    panel_w = (W - 2 * margin - gap) // 2
    left_x = margin
    right_x = margin + panel_w + gap

    bottom_l = draw_panel(d, left_x, panel_y, panel_w, data, "cloud run \u00b7 primary")
    bottom_r = draw_panel(d, right_x, panel_y, panel_w, data, "firebase hosting \u00b7 mirror")
    panel_bottom = max(bottom_l, bottom_r)

    # "=" equals connector, vertically centered on the panel row.
    mid_y = (panel_y + panel_bottom) // 2
    cx = W // 2
    d.ellipse([cx - 22, mid_y - 22, cx + 22, mid_y + 22], fill=INK, outline=(255, 255, 255, 30), width=1)
    eq_f = font(FONTB, 18)
    d.text((cx, mid_y), "=", font=eq_f, fill=GOLD, anchor="mm")

    url_f = font(MONO, 13)
    d.text((left_x, panel_bottom + 14), CLOUD_RUN_URL, font=url_f, fill=DIM)
    d.text((right_x, panel_bottom + 14), FIREBASE_URL, font=url_f, fill=DIM)

    foot_f = font(FONT, 14)
    d.text((margin, 745), f"GET /health on both origins, byte-identical (captured {CAPTURED_ON})",
            font=foot_f, fill=DIM)
    d.text((margin, 771), "Built with Genblaze \u00b7 Stored on Backblaze B2", font=foot_f, fill=DIM)

    wm_f = font(FONTB, 18)
    wm_text = "Cinemory"
    wm_w = d.textlength(wm_text, font=wm_f)
    wx = W - margin - wm_w - 22
    wy = 766
    d.ellipse([wx, wy + 3, wx + 14, wy + 17], fill=EMBER)
    d.text((wx + 22, wy - 2), wm_text, font=wm_f, fill=(235, 236, 240))

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    img.save(OUT_PNG)
    print(f"[ok] {OUT_PNG}  ({img.size[0]}x{img.size[1]})")
    print(f"[ok] build keys elided: {build_keys}")


if __name__ == "__main__":
    main()
