#!/usr/bin/env python3
"""Pick the narration voice with numbers instead of adjectives.

Why this exists
---------------
The first cut of the demo was described by its owner as sounding "military":
clipped, flat, and wrong for a product that turns your photos into a memory
film. Half of that was the script. The other half was the voice, and "warm"
is exactly the kind of word a voice marketplace puts on all of its voices, so
picking by description is picking blind.

So this script synthesizes the SAME line with every candidate voice and
measures the four things that separate a warm, unhurried read from a briefing:

  * ``wpm``          words per minute over the whole line. Lower is calmer.
  * ``artic wpm``    words per minute counting only the speaking, not the
                     silence. Separates "talks slowly" from "pauses a lot".
  * ``pause%``       share of the line that is silence, and the longest single
                     pause. A read that breathes scores high here.
  * ``spread st``    intonation range in semitones (10th to 90th percentile of
                     the pitch track) and its stddev. THIS is the monotony
                     number: a flat, declarative delivery has a narrow spread,
                     which is what "military" sounds like.
  * ``F0`` / ``bright``  median pitch, and the energy-weighted spectral
                     centroid. A lower centroid is a darker, warmer timbre.

Measured on the shipped beat-01 line (38 words, eleven_multilingual_v2, at
``build-video.py``'s own voice settings), sorted by intonation spread:

    voice            spread st   sd    wpm   artic  pause%  longest   F0  bright
    Alice                13.20  4.72  178.5  239.0   25.2%    0.58s  208    2436
    Matilda  <- chosen   12.12  4.29  187.4  275.4   31.9%    0.90s  202    2404
    Lily                 11.99  4.48  188.8  240.5   21.4%    0.46s  168    2485
    Rachel               11.16  4.10  193.3  262.1   26.1%    0.48s  176    2949
    Brian                 8.84  3.82  191.0  249.5   23.3%    0.86s   91    2384
    Adam     <- was       8.74  3.75  188.1  259.1   27.4%    0.88s  131    1934
    Will                  7.65  3.71  191.0  237.0   19.3%    0.86s  119    2197
    George                6.98  3.01  190.3  259.7   26.7%    0.88s  122    1915

Read that honestly, because it does not say quite what you would expect. The
voice the demo shipped with (Adam) has the DARKEST, warmest timbre in the set
(centroid 1934 Hz). Timbre was never the problem. Its intonation spread is 8.74
semitones, sixth of eight, against 12.12 for the voice now used: the old read
moves through about 40% less pitch, and a narrow range delivered over short
declarative sentences is exactly what "military" describes. The new default
also has the highest pause share (31.9%) and the longest single pause (0.90s),
which is what unhurried looks like as a number. Alice is the closest runner-up,
widest range of all and third on pause, and is one environment variable away.

Two caveats, stated plainly. RANKS NEAR A TIE MOVE BETWEEN RUNS, because every
synthesis is a fresh sample rather than a fixed rendering; what holds across
runs is that the old voice sits in the bottom third on both monotony measures
and the new one in the top two. And THESE ARE ACOUSTIC PROXIES: they can tell
you one read is flatter, faster or more clipped than another, never that it is
*likeable*. Run this script and listen to the mp3s it writes under
``demo/.voice-probe/`` (git-ignored, so a clone will not have them), then set
``ELEVENLABS_VOICE_ID`` and rebuild: the TTS cache is keyed on
(text, voice, model), so switching voices re-bills only what changed.

Deps:  numpy, ffmpeg on PATH.  Env: ELEVENLABS_API_KEY (text-to-speech scope).
Usage: python demo/pick-voice.py [--line "..."] [--voice name=id ...]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.request
import wave

import numpy as np

DEMO = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(DEMO, ".voice-probe")
MODEL = os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")

#: ElevenLabs stock voices, all reachable from any account with a TTS-scoped
#: key. Extend with --voice name=id.
CANDIDATES: dict[str, str] = {
    "matilda": "XrExE9yKIg1WjnnlVkGX",   # current default
    "adam": "pNInz6obpgDQGcFmaJgB",      # the previous default
    "alice": "Xb7hH8MSUJpSbSDYk0k2",
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "lily": "pFZP5JQG7iQjIQuC4Bku",
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "will": "bIHbv24MWmeRgasZH58o",
    "brian": "nPczCjzI2devNBz1zQrb",
}

DEFAULT_LINE = (
    "There is always one evening you wish you could keep. Give Cinemory the "
    "photos from that night and it hands you back a short film, with music, "
    "with titles, and with proof of where every frame came from."
)

#: MUST match ``build-video.py``'s synthesis settings. Stability alone moves a
#: voice's intonation spread by whole semitones, so comparing candidates at the
#: library defaults would measure a delivery the finished video never uses. Two
#: of the eight change rank between the defaults and these settings.
VOICE_SETTINGS = {"stability": 0.5, "similarity_boost": 0.8,
                  "style": 0.0, "use_speaker_boost": True}


def synth(voice_id: str, text: str, out_mp3: str, key: str) -> None:
    if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 3000:
        return
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    body = json.dumps({"text": text, "model_id": MODEL,
                       "voice_settings": VOICE_SETTINGS}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if len(data) < 3000:
        raise SystemExit(f"[STOP] suspiciously tiny audio for {voice_id} ({len(data)} bytes)")
    with open(out_mp3, "wb") as fh:
        fh.write(data)


def to_wav(mp3: str, out_wav: str) -> None:
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", mp3, "-ac", "1", "-ar", "22050",
                    "-f", "wav", out_wav], check=True)


def read_wav(path: str) -> tuple[int, np.ndarray]:
    with wave.open(path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64)
    return sr, x / 32768.0


def pitch_track(sr: int, x: np.ndarray) -> np.ndarray:
    """Voiced-frame F0 by autocorrelation. 40ms frames, 10ms hop, 70-350 Hz."""
    n, hop = int(0.04 * sr), int(0.01 * sr)
    lo, hi = int(sr / 350), int(sr / 70)
    out = []
    for i in range(0, len(x) - n, hop):
        f = x[i:i + n]
        if np.sqrt((f ** 2).mean()) < 0.02:
            continue
        f = f - f.mean()
        ac = np.correlate(f, f, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        k = int(np.argmax(ac[lo:hi])) + lo
        if ac[k] / ac[0] > 0.35:            # confident enough to call it voiced
            out.append(sr / k)
    return np.array(out)


def brightness(sr: int, x: np.ndarray) -> float:
    """Energy-weighted spectral centroid over voiced frames. Lower = warmer."""
    n, hop = 1024, 512
    w = np.hanning(n)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    num = den = 0.0
    for i in range(0, len(x) - n, hop):
        f = x[i:i + n]
        if np.sqrt((f ** 2).mean()) < 0.02:
            continue
        mag = np.abs(np.fft.rfft(f * w))
        e = float(mag.sum())
        if e <= 0:
            continue
        num += float((freqs * mag).sum() / e) * e
        den += e
    return num / den if den else 0.0


def silence_mask(sr: int, x: np.ndarray, frame_s: float = 0.02) -> np.ndarray:
    n = int(frame_s * sr)
    rms = np.array([np.sqrt((x[i:i + n] ** 2).mean()) for i in range(0, len(x) - n, n)])
    return rms < np.percentile(rms, 95) * 0.06


def longest_run(mask: np.ndarray, frame_s: float) -> float:
    best = cur = 0
    for s in mask:
        cur = cur + 1 if s else 0
        best = max(best, cur)
    return best * frame_s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", default=DEFAULT_LINE)
    ap.add_argument("--voice", action="append", default=[],
                    help="extra candidate as name=voice_id")
    args = ap.parse_args()

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("[STOP] ELEVENLABS_API_KEY is not set.")
    voices = dict(CANDIDATES)
    for spec in args.voice:
        name, _, vid = spec.partition("=")
        voices[name] = vid
    os.makedirs(PROBE, exist_ok=True)

    words = len(args.line.split())
    rows = []
    for name, vid in voices.items():
        mp3 = os.path.join(PROBE, f"{name}.mp3")
        wav = os.path.join(PROBE, f"{name}.wav")
        synth(vid, args.line, mp3, key)
        to_wav(mp3, wav)
        sr, x = read_wav(wav)
        dur = len(x) / sr
        sil = silence_mask(sr, x)
        speech_s = float((~sil).sum()) * 0.02
        f0 = pitch_track(sr, x)
        st = 12 * np.log2(f0 / np.median(f0))
        rows.append({
            "voice": name, "id": vid, "dur": dur,
            "wpm": words / dur * 60, "artic_wpm": words / speech_s * 60,
            "pause": float(sil.mean()), "longest_pause": longest_run(sil, 0.02),
            "spread_st": float(np.percentile(st, 90) - np.percentile(st, 10)),
            "sd_st": float(st.std()), "f0": float(np.median(f0)),
            "bright": brightness(sr, x),
        })

    rows.sort(key=lambda r: -r["spread_st"])
    print(f"{words} words · model {MODEL} · sorted by intonation spread (wide = expressive)\n")
    print(f"{'voice':<10}{'spread st':>10}{'sd':>6}{'wpm':>7}{'artic':>7}"
          f"{'pause%':>8}{'longest':>9}{'F0':>6}{'bright':>8}")
    for r in rows:
        print(f"{r['voice']:<10}{r['spread_st']:10.2f}{r['sd_st']:6.2f}{r['wpm']:7.1f}"
              f"{r['artic_wpm']:7.1f}{r['pause'] * 100:7.1f}%{r['longest_pause']:8.2f}s"
              f"{r['f0']:6.0f}{r['bright']:8.0f}")
    print(f"\nAudio written to {PROBE} (git-ignored). Listen before you disagree.")
    with open(os.path.join(PROBE, "measures.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
