# Cinemory — demo video

`cinemory-demo.mp4` is a **2:03** (122.97s) narrated walkthrough of the current
app, and the spine of it is **real screen footage of the deployed product
actually working**: 69.7s of the runtime, 57%, is live capture. It is built
beat-by-beat so the picture and the voice can never drift apart, and a CI gate
(`scripts/check_video.py`) fails the build if they do.

- **Voice:** ElevenLabs, voice `pNInz6obpgDQGcFmaJgB`, model `eleven_multilingual_v2`
  (the same clear, professional voice our other project demos use). Narration
  only. **No music**, deliberately: an unlicensed track is a copyright problem
  we are not going to hand a judge.
- **Picture:** five of the nine beats are live screen capture of
  https://cinemory-595784992266.europe-west1.run.app doing the real thing.
  The rest are the finished gallery cards, used only where evidence has to be
  legible and held still. No fabricated UI anywhere.
- **Sidecars (committed):** `cinemory-demo.en.srt` (full narration, per-beat
  windows) and `cinemory-demo.beats.json` (the machine-readable beat script and
  the single source of truth the gate checks against).

## Beats

| # | Beat | Picture | The line, in short |
|---|------|---------|--------------------|
| 1 | Hook | thumbnail card | Your memories, made into film, and sealed so anyone can prove it is real. |
| 2 | Photos in | **live footage** | The live app on Cloud Run; two AI-generated anniversary photos added; the order becomes the edit. |
| 3 | Occasion | **live footage** | Each occasion carries its own score, pacing and titles; Anniversary is picked and generate is pressed. |
| 4 | The live job | **live footage** | Each photo goes to Kling on GMI Cloud via Genblaze; a real model call, about five minutes a photo, polled in the background. |
| 5 | The reel plays | **live footage** | The generated reel plays, stitched from the two uploaded photos. |
| 6 | Provenance + Verify | **live footage** | The panel lists model, prompt and per-asset hashes; Verify recomputes the SHA-256 in the browser and the seal reads Verified. |
| 7 | What keeps it honest | B2 objects card | Every artifact sits in B2 at its own content hash; each clip cites its source photo; change a byte and the seal breaks. |
| 8 | The stack | architecture card | One core, three ports: Genblaze (Kling/seedance via GMI Cloud), Backblaze B2, FastAPI + React on Cloud Run, offline fakes in CI. |
| 9 | Close | live-health card | Live, open source, and it degrades in the open rather than faking a result. |

The exact spoken text for every beat lives in `cinemory-demo.beats.json` and
`cinemory-demo.en.srt`.

## The live footage

`demo/capture-live.py` drives the deployed app in the **system Chrome**
(`channel="chrome"` — no browser download) and records the journey to
`demo/.capture/` (git-ignored). `demo/cut-footage.py` then cuts the per-beat
clips committed under `video-assets/footage/`.

Three things worth knowing about that take:

- **It is one unbroken session.** The five footage beats are contiguous spans of
  a single run, in order. The only thing skipped is the multi-minute wait while
  the model renders, which beat 4 says out loud.
- **Two photos, not six.** The pipeline makes one live Kling image-to-video call
  per photo, and a single call measured **~314s** against the live service,
  while the frontend's poll ceiling is 12 minutes
  (`REEL_JOB_MAX_POLL_MS`). Two photos (~10.5 min) is the most that fits inside
  that ceiling, so it is the most the product can be shown doing for real in one
  continuous take. Three would trip the honest "taking longer than expected"
  degrade instead of showing a reel.
- **The capture self-checks.** Each phase has to supply at least as many seconds
  of picture as its beat's narration needs, or `capture-live.py` exits non-zero
  and says which phase was too quick. A too-fast take fails there, loudly,
  instead of quietly becoming a frozen frame in the finished video.

Capturing is done at 1280x720 CSS with a 2x device pixel ratio, so the layout is
the real desktop layout at native type size and the raster is downsampled into
the recording. Recording at 1920x1080 and scaling down afterwards shrinks every
glyph by a third and the UI copy stops being readable.

## The demo photos

`sample-data/anniversary/` holds six AI-generated scene photos of an anniversary
gathering, made through Cinemory's own provider adapter
(`GenblazeMediaProvider.generate(modality=IMAGE, model="seedream-5.0-lite")`).
The people in them are fictional and model-generated. Two of the six are
uploaded in the take. See [`sample-data/README.md`](../sample-data/README.md)
for how they were made, why they are safe, and the licence position.

They exist because the previous cut fed the pipeline `synthetic.py`'s abstract
colour gradients, so Kling faithfully animated nothing and a quarter of the
runtime was an empty screen with a caption over it.

## Smooth motion (the judder fix)

`zoompan` steps its crop origin in whole pixels of its *input*, so at the old
`scale=W*2:H*2` a slow zoom sat still for three or four frames and then lurched
half a pixel, about eight times a second. That was the tremble.

`demo/measure-motion.py` settles it with a number rather than an opinion: it
phase-correlates consecutive frames and reports the per-frame motion series.

| supersample | mean motion | JERK (stddev of per-frame change) |
|---|---|---|
| 2 (old) | 0.602 px/frame | **0.4130** — lurches of 0.87–1.04 px |
| 4 | 0.101 px/frame | 0.0542 |
| **8 (now)** | **0.030 px/frame** | **0.0207** — 20x smoother |

Footage beats get no synthetic move at all: their motion is the product moving.

## Rebuilding

```bash
pip install pillow                  # plus ffmpeg/ffprobe on PATH
export ELEVENLABS_API_KEY=...        # required; the build STOPS if it is missing

python demo/capture-live.py          # -> demo/.capture/journey.webm (+ marks)
python demo/cut-footage.py           # -> demo/video-assets/footage/*.mp4
python demo/build-video.py           # -> demo/cinemory-demo.mp4 (+ .en.srt + .beats.json)
```

Per-beat narration is cached by a hash of (text + voice + model), so tuning one
line never re-synthesizes or re-bills the others. Editing `BEATS` in
`build-video.py` regenerates the video and both sidecars together. Re-running
`cut-footage.py` after a narration edit re-cuts the clips to the new lengths.

## The sync gate (CI)

`python scripts/check_video.py` ffprobes the committed mp4 and cross-checks it
against the beat script. It fails the build when the video is over the 180s hard
cap, is not H.264/yuv420p 1280x720 ~30fps with a single AAC track, when the
SRT cues do not match the beats one-for-one in order, timing and text, or when
a beat-referenced asset carries a known-false marker (a stale capture whose
content went false later, e.g. the `fake-genblaze` cards this gate now
denylists by content hash). It needs only ffprobe and the standard library,
and runs as the `demo-video` CI job.

The beat-9 card (`video-assets/cards/cinemory-03-live-health.png`) is rendered
by `demo/render-health-card.py` from a real, saved `GET /health` capture
(`video-assets/health.txt`), not composited by hand. It shows the response
fields that hold across every deploy (`status`, `service`, `mode`, `provider`,
`storage`, both origins byte-identical) verbatim, and proves the `build` block
is real by showing its key names, but elides `commit`/`built_at` with an
ellipsis rather than a value that goes stale on the very next deploy. See
`demo/STATE.md` (2026-08-03 entry, "card no longer pins a build commit") for
why: committing a video that pins a commit hash changes the commit a redeploy
stamps, so the drift cannot be fixed by recapturing.

## The one remaining manual step

Upload `cinemory-demo.mp4` to YouTube (unlisted or public) and paste the URL into
the Devpost submission and `demo/SUBMISSION.md`.
