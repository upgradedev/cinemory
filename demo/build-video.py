#!/usr/bin/env python3
"""Build the Cinemory demo video — ElevenLabs narration, per-beat audio-locked.

Each script beat carries its own narration line. The build is BEAT-BY-BEAT so the
audio and the picture can never drift apart:

  1. Synthesize the beat's line with ElevenLabs (one professional voice for the
     whole video). Per-beat audio is cached by a hash of (text + voice + model),
     so re-running to tune one beat never re-synthesizes or re-bills the others.
  2. Decode to WAV, MEASURE the real narration length, then snap (length + a short
     tail) to a whole number of frames and pad with silence to exactly that many.
  3. The beat's PICTURE is rendered to the SAME frame-quantized length: a gentle
     Ken Burns move over a real, on-brand still (the finished gallery cards and
     real generated Kling frames), with a burned-in caption. Audio span == video
     span for every beat, frame-aligned, zero cumulative drift.
  4. Concatenate. Final duration == sum(beat durations) == the voiceover length.

Real assets only (committed under ``demo/video-assets/``): the six gallery cards
and three frames pulled straight from a real live generation run. No fabricated
UI. The stale ``203/21`` test-count card is deliberately not used.

Deliverables written next to this script:
  * ``cinemory-demo.mp4``       — the video (H.264 1280x720 30fps + AAC)
  * ``cinemory-demo.en.srt``    — caption sidecar, full narration per beat
  * ``cinemory-demo.beats.json``— the machine-readable beat/timing script

Deps:  Python 3.11+, Pillow, and ffmpeg/ffprobe on PATH.
Env:   ELEVENLABS_API_KEY  (required — no silent TTS fallback; the build STOPS
                            and reports if the key is missing or errors)
       ELEVENLABS_VOICE_ID (default pNInz6obpgDQGcFmaJgB — a clear pro voice,
                            the same one our other project demos use)
       ELEVENLABS_MODEL_ID (default eleven_multilingual_v2)
       FPS (default 30) · TAIL_SECONDS (default 0.45)

Usage:  python demo/build-video.py            # -> demo/cinemory-demo.mp4
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEMO = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(DEMO, "video-assets")
CARDS = os.path.join(ASSETS, "cards")
FRAMES = os.path.join(ASSETS, "frames")
WORK = os.path.join(DEMO, ".video-build")
CACHE = os.path.join(WORK, "tts-cache")

OUT_MP4 = os.path.join(DEMO, "cinemory-demo.mp4")
OUT_SRT = os.path.join(DEMO, "cinemory-demo.en.srt")
OUT_BEATS = os.path.join(DEMO, "cinemory-demo.beats.json")

W, H = 1280, 720
FPS = int(os.environ.get("FPS", "30"))
TAIL = float(os.environ.get("TAIL_SECONDS", "0.45"))
VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID") or "pNInz6obpgDQGcFmaJgB"
MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2"

FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE", "ffprobe")

# Brand palette (matches the gallery cards).
INK = (11, 13, 20)
WHITE = (244, 244, 246)
EMBER = (233, 84, 74)
GOLD = (212, 169, 78)
ZINC = (198, 200, 208)


def _first_font(*candidates: str) -> str:
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[-1]


FONT = _first_font("C:/Windows/Fonts/segoeui.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONTB = _first_font("C:/Windows/Fonts/segoeuib.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


# --------------------------------------------------------------------------- #
# The script — one beat per picture, honest to the current app.
# --------------------------------------------------------------------------- #
@dataclass
class Beat:
    id: str
    assets: list[str]          # one still = Ken Burns; several = a mini montage
    caption: str               # short burned-in line
    narration: str             # spoken + the SRT cue
    dur: float = field(default=0.0, init=False)


def card(name: str) -> str:
    return os.path.join(CARDS, name)


def frame(name: str) -> str:
    return os.path.join(FRAMES, name)


BEATS: list[Beat] = [
    Beat(
        "01-hook",
        [card("cinemory-01-thumbnail.png")],
        "Cinemory — memories, made into film",
        "Your memories, made into film. And sealed, so anyone can prove it's "
        "real. This is Cinemory. It began as an anniversary gift, turning a "
        "folder of photos into a short film you could actually keep.",
    ),
    Beat(
        "02-trust",
        [frame("frame-clip1-kling.png")],
        "Easy to make. Hard to trust.",
        "Generative video like this is easy to make, and hard to trust. When an "
        "AI turns your photos into a highlight reel, three questions matter. "
        "Which model made it. From which photos. And can you prove that not one "
        "frame was changed?",
    ),
    Beat(
        "03-what",
        [card("cinemory-02-pipeline.png")],
        "Photos in. A scored reel out. Provenance sealed.",
        "Cinemory answers all three. You give it photos, you pick an occasion, "
        "and it returns a scored, cinematic reel. Every clip is stored on "
        "Backblaze B2 at its own hash, and sealed with SHA-256 provenance, so "
        "the record of how it was made travels with the video.",
    ),
    Beat(
        "04-reel",
        [frame("frame-clip4-kling.png"), frame("frame-livebox-upload-kling.png")],
        "Four steps: photos, occasion, generate, play",
        "It runs in four steps. Add your photos, choose an occasion that sets "
        "the music and the pacing, hit generate, and the reel plays. Real clips, "
        "animated from each photo, bridged and graded into one film.",
    ),
    Beat(
        "05-verify",
        [card("cinemory-05-provenance.png")],
        "Press Verify — the seal recomputes to Verified",
        "Then open the Provenance panel. It shows the model, the prompt, and a "
        "hash for every step. Press Verify, and your browser recomputes the "
        "SHA-256 itself. The seal flips to Verified. A server re-check then "
        "re-hashes every stored file and reports each check as passed.",
    ),
    Beat(
        "06-honest",
        [card("cinemory-04-b2-objects.png")],
        "Every clip cites its source photo, by hash",
        "Two things keep it honest. Every clip cites the exact source photo it "
        "came from, by hash. Change a single byte, and the seal breaks. And when "
        "a live model is down, Cinemory degrades in the open, records the "
        "provider it actually used, and never fakes a result.",
    ),
    Beat(
        "07-stack",
        [card("cinemory-06-architecture.png")],
        "One core, three ports. Live adapters, offline fakes.",
        "The design is one clean core with three ports. Genblaze drives Kling "
        "and seedance through GMI Cloud. Backblaze B2 holds every artifact "
        "behind a queryable index. FastAPI and React run on Cloud Run. And "
        "offline fakes run the whole pipeline in tests, with no credentials.",
    ),
    Beat(
        "08-close",
        [card("cinemory-03-live-proof.png")],
        "Live now · open source · github.com/upgradedev/cinemory",
        "It's live on Cloud Run, mirrored on Firebase, and fully open source. "
        "Cinemory. Memories, made into film, that you can trust.",
    ),
]


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        sys.stderr.write("CMD FAILED: " + " ".join(map(str, cmd)) + "\n")
        sys.stderr.write(r.stderr.decode(errors="replace")[-1600:] + "\n")
        raise SystemExit(1)
    return r.stdout.decode(errors="replace")


def probe_duration(path: str) -> float:
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


# --------------------------------------------------------------------------- #
# ElevenLabs (no silent fallback — the build STOPS on any TTS error)
# --------------------------------------------------------------------------- #
def synth_elevenlabs(text: str, out_mp3: str, key: str, retries: int = 3) -> None:
    """Cached, retried ElevenLabs TTS. Cache key = sha256(text|voice|model)."""
    digest = hashlib.sha256(f"{text}|{VOICE_ID}|{MODEL_ID}".encode()).hexdigest()[:16]
    cached = os.path.join(CACHE, digest + ".mp3")
    if os.path.exists(cached) and os.path.getsize(cached) > 3000:
        _copy(cached, out_mp3)
        print(f"[tts] cache hit  {digest}")
        return

    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
           f"?output_format=mp3_44100_128")
    body = json.dumps({
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                           "style": 0.0, "use_speaker_boost": True},
    }).encode("utf-8")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "xi-api-key": key, "Content-Type": "application/json",
                "Accept": "audio/mpeg"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if len(data) < 3000:
                raise RuntimeError(f"suspiciously tiny audio ({len(data)} bytes)")
            with open(cached, "wb") as fh:
                fh.write(data)
            _copy(cached, out_mp3)
            return
        except urllib.error.HTTPError as e:  # noqa: PERF203
            detail = e.read().decode(errors="replace")[:400]
            last = RuntimeError(f"HTTP {e.code}: {detail}")
            if e.code in (401, 403, 422):  # auth/quota/validation — don't hammer
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise SystemExit(
        f"[STOP] ElevenLabs TTS failed for beat text {text[:48]!r}: {last}\n"
        f"       Set a valid ELEVENLABS_API_KEY. No edge-tts fallback by design."
    )


def _copy(src: str, dst: str) -> None:
    with open(src, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())


def build_audio(beats: list[Beat], key: str) -> tuple[str, list[float]]:
    """Synthesize + measure + frame-snap + pad each beat; concat the voiceover."""
    padded, durations = [], []
    for i, b in enumerate(beats):
        mp3 = os.path.join(WORK, f"nar_{i:02d}.mp3")
        synth_elevenlabs(b.narration, mp3, key)
        wav = os.path.join(WORK, f"nar_{i:02d}.wav")
        run([FFMPEG, "-y", "-i", mp3, "-ac", "1", "-ar", "44100", "-f", "wav", wav])
        d = probe_duration(wav)
        frames = max(1, round((d + TAIL) * FPS))
        dur = frames / FPS
        pad = os.path.join(WORK, f"pad_{i:02d}.wav")
        run([FFMPEG, "-y", "-i", wav, "-af", "apad", "-t", f"{dur:.6f}",
             "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", "-f", "wav", pad])
        padded.append(pad)
        durations.append(dur)
        b.dur = dur
        print(f"[audio] {b.id:<10} speech={d:6.3f}s  scene={dur:6.3f}s")

    listf = os.path.join(WORK, "audio_concat.txt")
    with open(listf, "w", encoding="utf-8") as fh:
        for p in padded:
            fh.write(f"file '{p}'\n")
    voice = os.path.join(WORK, "voiceover.wav")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listf,
         "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", voice])
    return voice, durations


# --------------------------------------------------------------------------- #
# Picture: Pillow composites + ffmpeg Ken Burns + burned caption
# --------------------------------------------------------------------------- #
def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / im.width, h / im.height)
    r = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((left, top, left + w, top + h))


def compose_base(src: str, is_card: bool) -> Image.Image:
    """A full 1280x720 still. Cards are letterboxed onto a blurred fill of
    themselves (invisible pillarbox, fully legible); real 16:9 frames fill."""
    im = Image.open(src).convert("RGB")
    if not is_card:
        return _cover(im, W, H)
    bg = _cover(im, W, H).filter(ImageFilter.GaussianBlur(30))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.42)
    fscale = min(W / im.width, H / im.height) * 0.93
    fg = im.resize((round(im.width * fscale), round(im.height * fscale)), Image.LANCZOS)
    canvas = bg.copy()
    canvas.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    return canvas


def caption_overlay(text: str, show_wordmark: bool) -> Image.Image:
    """Transparent 1280x720: a lower-third caption band + caption text, and (only
    on the otherwise-unbranded photo beats) a small brand wordmark. Overlaid AFTER
    the Ken Burns zoom, so it stays crisp and fixed. The band ramps to near-solid
    at the bottom so it cleanly covers each gallery card's own footer."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    band_h = 190
    for y in range(band_h):
        p = y / band_h
        # ramp to fully opaque by ~2/3 down, so the band covers each card's
        # own footer line cleanly while the top edge still fades in softly.
        a = int(236 * min(1.0, (p * 1.5) ** 1.3))
        d.line([(0, H - band_h + y), (W, H - band_h + y)], fill=(6, 7, 11, a))
    # caption (shrink to fit)
    size = 33
    while size > 20:
        fnt = font(FONTB, size)
        if d.textlength(text, font=fnt) <= W - 150:
            break
        size -= 1
    fnt = font(FONTB, size)
    tw = d.textlength(text, font=fnt)
    ty = H - 64
    # gold accent bar above the caption
    d.rectangle([(W - 64) / 2, ty - 22, (W + 64) / 2, ty - 19], fill=GOLD + (255,))
    d.text(((W - tw) / 2, ty), text, font=fnt, fill=WHITE + (255,))
    # brand wordmark, top-left — only on photo beats (the cards are self-branded)
    if show_wordmark:
        wf = font(FONTB, 24)
        d.ellipse([40, 42, 54, 56], fill=EMBER + (255,))
        d.text((64, 38), "Cinemory", font=wf, fill=(235, 236, 240, 235))
    return ov


def frame_split(total_frames: int, n: int) -> list[int]:
    """Split total_frames into n parts; the last part absorbs the remainder so
    the montage sums EXACTLY to the beat's frame-locked length."""
    base = total_frames // n
    parts = [base] * n
    parts[-1] += total_frames - base * n
    return parts


def kenburns(base_png: str, out_mp4: str, frames: int, zoom_in: bool) -> None:
    """One still -> exact `frames`-long clip with a gentle center Ken Burns."""
    zmax = 1.08
    if zoom_in:
        z = f"min(zoom+{(zmax - 1.0) / max(frames - 1, 1):.6f},{zmax})"
    else:  # start zoomed, ease out to full frame
        z = f"if(eq(on,0),{zmax},max(zoom-{(zmax - 1.0) / max(frames - 1, 1):.6f},1.0))"
    vf = (f"scale={W * 2}:{H * 2},"
          f"zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
          f"s={W}x{H}:fps={FPS},format=yuv420p")
    run([FFMPEG, "-y", "-loop", "1", "-i", base_png, "-t", f"{frames / FPS:.6f}",
         "-vf", vf, "-r", str(FPS), "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         out_mp4])


def render_beat(idx: int, beat: Beat, dur: float) -> str:
    """Ken Burns motion (single still or montage) + burned caption -> seg mp4."""
    frames = round(dur * FPS)
    # 1) motion (video only, exact length)
    motion = os.path.join(WORK, f"motion_{idx:02d}.mp4")
    subs = []
    parts = frame_split(frames, len(beat.assets))
    for j, (asset, pf) in enumerate(zip(beat.assets, parts, strict=True)):
        base_png = os.path.join(WORK, f"base_{idx:02d}_{j}.png")
        compose_base(asset, is_card="/cards/" in asset.replace(os.sep, "/")).save(base_png)
        sub = os.path.join(WORK, f"sub_{idx:02d}_{j}.mp4")
        kenburns(base_png, sub, pf, zoom_in=((idx + j) % 2 == 0))
        subs.append(sub)
    if len(subs) == 1:
        motion = subs[0]
    else:
        cat = os.path.join(WORK, f"motion_concat_{idx:02d}.txt")
        with open(cat, "w", encoding="utf-8") as fh:
            for s in subs:
                fh.write(f"file '{s}'\n")
        run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", cat,
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", motion])
    # 2) burn caption + mux this beat's padded audio. The brand wordmark rides
    #    only on photo beats; the gallery cards are already self-branded.
    is_card_beat = any("/cards/" in a.replace(os.sep, "/") for a in beat.assets)
    cap_png = os.path.join(WORK, f"cap_{idx:02d}.png")
    caption_overlay(beat.caption, show_wordmark=not is_card_beat).save(cap_png)
    audio = os.path.join(WORK, f"pad_{idx:02d}.wav")
    seg = os.path.join(WORK, f"seg_{idx:02d}.mp4")
    run([FFMPEG, "-y", "-i", motion, "-i", cap_png, "-i", audio,
         "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
         "-map", "[v]", "-map", "2:a", "-t", f"{dur:.6f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100", seg])
    return seg


# --------------------------------------------------------------------------- #
# Sidecars: SRT + beats.json
# --------------------------------------------------------------------------- #
def srt_ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_sidecars(beats: list[Beat], durations: list[float]) -> None:
    cues, meta, t = [], [], 0.0
    for i, (b, dur) in enumerate(zip(beats, durations, strict=True), start=1):
        start, end = t, t + dur
        text = "\n".join(textwrap.wrap(" ".join(b.narration.split()), width=64))
        cues.append(f"{i}\n{srt_ts(start)} --> {srt_ts(end)}\n{text}\n")
        meta.append({
            "index": i, "id": b.id,
            "assets": [os.path.relpath(a, DEMO).replace(os.sep, "/") for a in b.assets],
            "caption": b.caption, "narration": " ".join(b.narration.split()),
            "start": round(start, 3), "end": round(end, 3), "dur": round(dur, 3),
        })
        t = end
    with open(OUT_SRT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(cues))
    with open(OUT_BEATS, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({
            "video": os.path.basename(OUT_MP4),
            "srt": os.path.basename(OUT_SRT),
            "fps": FPS, "width": W, "height": H,
            "voice": {"provider": "elevenlabs", "voice_id": VOICE_ID, "model_id": MODEL_ID},
            "total_seconds": round(sum(durations), 3),
            "beats": meta,
        }, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# --------------------------------------------------------------------------- #
def main() -> int:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit(
            "[STOP] ELEVENLABS_API_KEY is not set. This build is ElevenLabs-only "
            "(no edge-tts fallback by design). Export the key and re-run."
        )
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)

    chars = sum(len(b.narration) for b in BEATS)
    print(f"[build] {len(BEATS)} beats · {chars} narration chars · fps={FPS} · tail={TAIL}s")
    print(f"[voice] elevenlabs voice_id={VOICE_ID} model_id={MODEL_ID}")

    _voice, durations = build_audio(BEATS, key)

    segs = [render_beat(i, b, d) for i, (b, d) in enumerate(zip(BEATS, durations, strict=True))]

    listf = os.path.join(WORK, "video_concat.txt")
    with open(listf, "w", encoding="utf-8") as fh:
        for s in segs:
            fh.write(f"file '{s}'\n")
    # Concat to a fresh temp, then swap into place. On Windows the destination mp4
    # can hold a lingering read/AV handle right after a previous build; encoding to
    # a new name and atomically replacing avoids ffmpeg fighting a locked output.
    tmp_out = os.path.join(WORK, "final.mp4")
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", listf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
         "-movflags", "+faststart", tmp_out])
    for attempt in range(5):
        try:
            os.replace(tmp_out, OUT_MP4)
            break
        except OSError as e:  # destination briefly locked — back off and retry
            if attempt == 4:
                raise SystemExit(f"[STOP] could not replace {OUT_MP4}: {e}") from e
            time.sleep(1.5)

    write_sidecars(BEATS, durations)

    total = sum(durations)
    vdur = probe_duration(OUT_MP4)
    print(f"\n[guard] beats={len(BEATS)} sum={total:.3f}s  video={vdur:.3f}s  chars={chars}")
    if abs(vdur - total) > (1.0 / FPS) + 0.20:
        raise SystemExit(f"[STOP] video {vdur:.3f}s vs sum {total:.3f}s drift too large")
    if vdur >= 180.0:
        raise SystemExit(f"[STOP] video {vdur:.3f}s exceeds the 180s hard cap")
    mm, ss = divmod(vdur, 60)
    print(f"[ok] {OUT_MP4}  {int(mm)}:{ss:04.1f}  ({chars} chars sent to ElevenLabs)")
    print(f"[ok] {OUT_SRT}")
    print(f"[ok] {OUT_BEATS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
