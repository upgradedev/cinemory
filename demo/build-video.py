#!/usr/bin/env python3
"""Build the Cinemory demo mp4 from real captured outputs + edge-tts narration.

Fully automatable, no paid services:
  * slides + terminal panels rendered with Pillow,
  * free narration via edge-tts,
  * composed with ffmpeg.

The terminal panels show the ACTUAL captured command output committed under
``demo/video-assets/`` (regenerate them with ``demo/capture-demo.sh`` +
``pytest`` + a couple of ``curl`` calls against the live service). There is no
live-browser segment — the React-wizard shot is left as a precise shot-list in
``demo/video-script.md`` (add Playwright ``recordVideo`` to automate it).

Usage:  pip install pillow edge-tts   # plus ffmpeg on PATH
        python demo/build-video.py            # -> demo/cinemory-demo.mp4
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import edge_tts

DEMO = Path(__file__).resolve().parent
CAP = DEMO / "video-assets"
WORK = DEMO / ".video-build"
WORK.mkdir(exist_ok=True)
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else (DEMO / "cinemory-demo.mp4")

W, H = 1280, 720
BG = (11, 11, 13)
PANEL = (18, 18, 22)
PANEL_BAR = (28, 28, 34)
GOLD = (212, 169, 78)
ZINC = (212, 212, 216)
ZINC_DIM = (140, 140, 150)
GREEN = (74, 222, 128)
RED = (248, 113, 113)
BLUE = (125, 176, 232)

def _first_font(*candidates: str) -> str:
    for c in candidates:
        if Path(c).exists():
            return c
    return candidates[-1]  # let PIL raise a clear error if truly none exist


FONT = _first_font("C:/Windows/Fonts/segoeui.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONTB = _first_font("C:/Windows/Fonts/segoeuib.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MONO = _first_font("C:/Windows/Fonts/consola.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
MONOB = _first_font("C:/Windows/Fonts/consolab.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf")
VOICE = "en-US-GuyNeural"


def f(path, size):
    return ImageFont.truetype(path, size)


def new_frame():
    return Image.new("RGB", (W, H), BG)


def letterbox(d):
    d.rectangle([0, 0, W, 46], fill=(0, 0, 0))
    d.rectangle([0, H - 46, W, H], fill=(0, 0, 0))


def center_text(d, cx, y, text, font, fill):
    b = d.textbbox((0, 0), text, font=font)
    d.text((cx - (b[2] - b[0]) / 2, y), text, font=font, fill=fill)


def slide_title(title, subtitle, tag=None):
    img = new_frame()
    d = ImageDraw.Draw(img)
    letterbox(d)
    # gold rule
    d.rectangle([W / 2 - 40, 250, W / 2 + 40, 253], fill=GOLD)
    center_text(d, W / 2, 285, title, f(FONTB, 60), ZINC)
    if subtitle:
        center_text(d, W / 2, 375, subtitle, f(FONT, 30), ZINC_DIM)
    if tag:
        center_text(d, W / 2, 620, tag, f(MONO, 22), GOLD)
    return img


def slide_bullets(header, bullets, footer=None):
    img = new_frame()
    d = ImageDraw.Draw(img)
    d.text((110, 90), header, font=f(FONTB, 44), fill=ZINC)
    d.rectangle([110, 158, 260, 162], fill=GOLD)
    y = 220
    for label, desc in bullets:
        d.text((120, y), "●", font=f(FONT, 26), fill=GOLD)
        d.text((165, y - 4), label, font=f(FONTB, 30), fill=ZINC)
        if desc:
            d.text((165, y + 36), desc, font=f(FONT, 24), fill=ZINC_DIM)
        y += 108
    if footer:
        d.text((120, H - 96), footer, font=f(MONO, 22), fill=GOLD)
    return img


def _color_for(line):
    ls = line.strip()
    if "True" in line or "PASSED" in line or '"status":"ok"' in line or "200" in line:
        return GREEN
    if "FAILED" in line or "AccessDenied" in line or "Error" in line:
        return RED
    if ls.startswith("$") or ls.startswith("#") or ls.startswith("▶"):
        return GOLD
    return ZINC


def terminal(header, cmd, lines, note=None, mono_size=22):
    img = new_frame()
    d = ImageDraw.Draw(img)
    d.text((110, 66), header, font=f(FONTB, 38), fill=ZINC)
    # panel
    x0, y0, x1, y1 = 90, 140, W - 90, H - 96
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=PANEL)
    d.rounded_rectangle([x0, y0, x1, y0 + 40], radius=14, fill=PANEL_BAR)
    d.rectangle([x0, y0 + 26, x1, y0 + 40], fill=PANEL_BAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([x0 + 18 + i * 22, y0 + 14, x0 + 30 + i * 22, y0 + 26], fill=c)
    d.text((x0 + 96, y0 + 11), "bash — cinemory", font=f(MONO, 18), fill=ZINC_DIM)
    fm = f(MONO, mono_size)
    y = y0 + 62
    if cmd:
        d.text((x0 + 26, y), "$ ", font=f(MONOB, mono_size), fill=GREEN)
        d.text((x0 + 26 + 22, y), cmd, font=f(MONOB, mono_size), fill=ZINC)
        y += mono_size + 12
    for ln in lines:
        d.text((x0 + 26, y), ln, font=fm, fill=_color_for(ln))
        y += mono_size + 8
    if note:
        d.text((110, H - 78), note, font=f(FONT, 22), fill=ZINC_DIM)
    return img


def read_lines(name, maxn=14):
    txt = (CAP / name).read_text(encoding="utf-8", errors="replace")
    out = []
    for ln in txt.splitlines():
        ln = ln.rstrip()
        if len(ln) > 78:
            ln = ln[:75] + "..."
        out.append(ln)
    return out[:maxn]


async def synth(text, path):
    c = edge_tts.Communicate(text, VOICE, rate="-4%")
    await c.save(str(path))


def duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


# ── segments ──────────────────────────────────────────────────────────────────
def build_segments():
    segs = []

    segs.append((
        slide_title("Cinemory", "your memories, made into film",
                    "generated with Genblaze · stored on Backblaze B2 · SHA-256 provenance"),
        "Cinemory turns your photos into a scored cinematic film. Generated with "
        "Genblaze, stored on Backblaze B2, and sealed with verifiable SHA-256 "
        "provenance on every frame it produces. It started as an anniversary gift; "
        "the personal content stays private, so this demo uses synthetic photos only.",
    ))

    segs.append((
        slide_bullets("AI media is easy to make — and hard to trust", [
            ("What made this?", "which model, prompt and parameters produced the reel"),
            ("From what inputs?", "every source photo, content-addressed"),
            ("Can I prove it wasn't tampered with?", "a seal that fails loudly if a byte changes"),
        ], footer="Cinemory answers all three."),
        "AI media is easy to make and hard to trust. For a comms team turning an "
        "event's photos into a branded highlight reel, three questions matter: what "
        "made this, from what inputs, and can I prove it wasn't tampered with. "
        "Cinemory answers all three.",
    ))

    segs.append((
        slide_bullets("The product — a four-step cinematic wizard", [
            ("Photos", "drag-drop your real photos; the actual bytes are the input"),
            ("Occasion", "presets set music, pacing and aspect ratio"),
            ("Generate", "real bytes stream to POST /reels/upload-multipart"),
            ("Result + Provenance", "the reel plays; per-step hashes + the manifest seal"),
        ], footer="Live: upgradegr-cinemory.web.app"),
        "The product is a four-step cinematic wizard. You drag and drop your real "
        "photos onto the storyboard; the actual pixels are the input, not just a "
        "count. You pick an occasion, which sets the music mood, pacing and aspect "
        "ratio. You hit generate, and the real photo bytes stream to the upload "
        "endpoint. The reel plays, and a provenance panel shows every step's hash "
        "and the manifest seal.",
    ))

    segs.append((
        terminal("The pipeline in the raw", "bash demo/capture-demo.sh",
                 read_lines("cli.txt"),
                 note="17 objects persisted; manifest, asset and embedded provenance all verify."),
        "Under the hood, the same pipeline runs from the command line. Each photo "
        "becomes a short clip through a Genblaze pipeline step, chapters are bridged "
        "with first-last-frame transitions, and the reel is stitched. Every artifact "
        "is content-addressed and stored — Backblaze B2 in live mode, an in-memory "
        "store here, so this whole run works offline with no credentials. Seventeen "
        "objects are stored, and the manifest, the asset and the embedded provenance "
        "all verify — true, true, true.",
    ))

    segs.append((
        terminal("Provenance is real", "cat manifest.json  # first step",
                 read_lines("manifest.txt"),
                 note="Provider, model, modality, per-asset SHA-256 — sealed into a manifest."),
        "Provenance isn't a badge; it's data. The manifest records the provider, the "
        "model, the modality and a SHA-256 hash for every asset, timestamped, and it "
        "is embedded into the reel container so it re-verifies offline with no network.",
    ))

    segs.append((
        terminal("Tamper-evident by test", "pytest tests/unit/test_provenance.py -v",
                 read_lines("tamper.txt"),
                 note="Flip one byte and verification fails — trust is a passing test."),
        "And it's tamper-evident. Flip a single byte in a sealed asset and "
        "verification fails. Trust isn't a claim here; it's a test that runs in CI — "
        "including the one that proves tampering is detected.",
    ))

    segs.append((
        terminal("The core action never 500s", "curl /health   &&   POST /reels",
                 read_lines("health.txt", 2) + [""] + read_lines("reels.txt", 6),
                 note="Live mode uses real backends only when creds are present; else it degrades to 200."),
        "Production readiness starts with never failing the core action. In live "
        "mode the API uses the real Genblaze and B2 backends only when their "
        "credentials are present, and otherwise degrades transparently to the "
        "offline path. Health reports the effective provider and storage, and a "
        "reel request returns two hundred with a sealed manifest even with no "
        "credentials.",
    ))

    segs.append((
        terminal("Verified against the real SDK",
                 "pytest tests/integration/test_genblaze_contract.py -v",
                 read_lines("contract.txt"),
                 note="154 tests green offline; the adapter runs against the real Genblaze SDK."),
        "The whole suite runs green offline with zero credentials — a hundred and "
        "fifty-four tests — including a contract test that runs the adapter against "
        "the real published Genblaze SDK, so any API drift fails CI.",
    ))

    segs.append((
        slide_title("Memories, made into film — that you can trust",
                    "Genblaze generation · B2 storage + queryable index · verifiable provenance",
                    "github.com/upgradedev/cinemory · upgradegr-cinemory.web.app"),
        "Genblaze for generation and per-asset provenance; Backblaze B2 for durable, "
        "content-addressed storage of every artifact plus a queryable run index; and "
        "provenance you can verify, that fails loudly when tampered. That's Cinemory "
        "— memories, made into film, that you can trust.",
    ))

    return segs


def main():
    segs = build_segments()
    parts = []
    for i, (img, narration) in enumerate(segs):
        png = WORK / f"seg{i:02d}.png"
        img.save(png)
        mp3 = WORK / f"seg{i:02d}.mp3"
        asyncio.run(synth(narration, mp3))
        dur = duration(mp3) + 0.7
        seg_mp4 = WORK / f"seg{i:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(mp3),
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-r", "30", "-t", f"{dur:.2f}",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            "-af", "apad", "-shortest",
            "-vf", f"scale={W}:{H}", str(seg_mp4),
        ], check=True, capture_output=True)
        parts.append(seg_mp4)
        print(f"  seg{i:02d}: {dur:.1f}s")

    listf = WORK / "concat.txt"
    listf.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(OUT),
    ], check=True, capture_output=True)
    print("total:", duration(OUT), "s ->", OUT)


if __name__ == "__main__":
    main()
