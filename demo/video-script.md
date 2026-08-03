# Cinemory — demo video

`cinemory-demo.mp4` is a **2:34** (154.00s) narrated walkthrough of the current
app, and the spine of it is **real screen footage of the deployed product
actually working**: 68.2s of the runtime is live capture. It is built
beat-by-beat so the picture and the voice can never drift apart, and a CI gate
(`scripts/check_video.py`) fails the build if they do.

- **Voice:** ElevenLabs, voice `21m00Tcm4TlvDq8ikWAM` (Rachel), model
  `eleven_multilingual_v2`. Narration only. **No music**, deliberately: an
  unlicensed track is a copyright problem we are not going to hand a judge.
- **Why that voice.** The first cut used `pNInz6obpgDQGcFmaJgB` and sounded, in
  its owner's word, "military": clipped and flat, which is the wrong register
  for a memory film. `demo/pick-voice.py` reads the shipped beat-01 line in
  eight stock voices, at `build-video.py`'s own voice settings, and measures
  pace, articulation rate, pause share, longest pause, intonation spread and
  timbre.

  **The numbers narrowed the field; a person picked the voice.** Rachel ranks
  fourth of eight on intonation spread, so a script that ranked by the metric
  alone would not have chosen her. The measurement is good for ruling out the
  flat original and for proving the swap actually shipped, and it is a poor
  judge of whether a voice suits a film about someone's anniversary. That call
  was made by ear, which is the right instrument for it.

  | voice | spread st | sd | wpm | pause% | longest | timbre Hz |
  |---|---|---|---|---|---|---|
  | Alice | 13.20 | 4.72 | 178.5 | 25.2% | 0.58s | 2436 |
  | Matilda | 12.12 | 4.29 | 187.4 | 31.9% | 0.90s | 2404 |
  | Lily | 11.99 | 4.48 | 188.8 | 21.4% | 0.46s | 2485 |
  | **Rachel (now)** | 11.16 | 4.10 | 193.3 | 26.1% | 0.48s | 2949 |
  | Brian | 8.84 | 3.82 | 191.0 | 23.3% | 0.86s | 2384 |
  | **Adam (was)** | **8.74** | 3.75 | 188.1 | 27.4% | 0.88s | **1934** |
  | Will | 7.65 | 3.71 | 191.0 | 19.3% | 0.86s | 2197 |
  | George | 6.98 | 3.01 | 190.3 | 26.7% | 0.88s | 1915 |

  The old voice has the **darkest, warmest timbre in the set**, so timbre was
  never the problem. Its intonation range is 8.74 semitones, sixth of eight,
  against 11.16 for Rachel: about 28% more pitch movement, and it is that
  flatness delivered over short declarative sentences that "military" describes.
  Two honest caveats:
  ranks near a tie move between runs because each synthesis is a fresh sample,
  and these are acoustic proxies, not taste. Run `python demo/pick-voice.py` and
  listen to the mp3s it writes under `demo/.voice-probe/` before you disagree,
  then set `ELEVENLABS_VOICE_ID` and rebuild: the TTS cache is keyed on
  (text, voice, model), so a voice change re-bills only what changed.
- **Picture:** five of the nine beats are live screen capture of
  https://cinemory-595784992266.europe-west1.run.app doing the real thing.
  The rest are the finished gallery cards, used only where evidence has to be
  legible and held still. No fabricated UI anywhere.
- **Sidecars (committed):** `cinemory-demo.en.srt` (full narration, per-beat
  windows) and `cinemory-demo.beats.json` (the machine-readable beat script and
  the single source of truth the gate checks against).

## Beats

| # | Beat | Picture | Length | The line, in short | Judging criterion |
|---|------|---------|--------|--------------------|-------------------|
| 1 | Hook | thumbnail card | 12.8s | The evening you wish you could keep, handed back as a short film with proof of where every frame came from. | Utility |
| 2 | Photos in | **live footage** | 12.9s | The real app on Cloud Run; two anniversary photos dropped in; no account, no watermark; the photos go to a private Backblaze bucket. | Utility · B2 |
| 3 | Occasion | **live footage** | 11.9s | Each occasion brings its own music, pacing and titles, including one for award nights and company events. | Utility |
| 4 | The live job | **live footage** | 14.8s | Each photo becomes a Genblaze pipeline step and goes to Kling on GMI Cloud; a real model call, about five minutes a photo, run as a background job the page polls. | Genblaze · production readiness |
| 5 | The reel plays | **live footage** | 10.1s | Two photographs, now moving, cut to the music; everyone in them is model generated. | Utility |
| 6 | Provenance + Verify | **live footage** | 18.5s | The panel lists every step, model, prompt and per-asset hash; Verify recomputes the SHA-256 in the browser; all nine checks pass and you can run them yourself. | Production readiness |
| 7 | Storage + seal | B2 objects card | 25.2s | Everything lands in B2 at its own content hash, every clip names the photo it came from, Genblaze seals its own provenance beside ours, and an append-only index makes the bucket queryable. | B2 · Genblaze |
| 8 | The stack | architecture card | 24.0s | One core, three ports, offline fakes with no credentials, Genblaze contract tested against the real SDK, 600+ tests and security scans on every push. | Production readiness · Genblaze |
| 9 | Close | live-health card | 23.7s | Every push to main deploys itself and only passes if the live service reports that commit; a model outage is said out loud, not faked. | Production readiness · Utility |

The exact spoken text for every beat lives in `cinemory-demo.beats.json` and
`cinemory-demo.en.srt`.

**Criterion coverage**, allocating each beat's seconds across the sentences in
it: real-world utility **32%**, production readiness **36%**, Backblaze B2 **16%**,
Genblaze **16%**. Every one of the four judged criteria gets its own
minute-fraction rather than a passing mention. Shares are quoted rather than
seconds because each re-synthesis shifts the absolute lengths by a little.

**On the balance of picture.** Live footage is 68.2s of the 154.00s runtime.
That is more live-app seconds than the previous cut (67.9s) but a smaller
share of it (44% vs 55%), because the added narration went onto the three
evidence cards at the end, where B2, the architecture and the live `/health`
have to be legible and held still. The five footage beats are the same clips
and every one of them is still **shorter than its source clip** (slack 0.30s to
0.87s), so no beat freezes on a cloned frame and the capture self-check
invariant below still holds.

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

python demo/pick-voice.py            # optional: compare narration voices by measurement
python demo/capture-live.py          # -> demo/.capture/journey.webm (+ marks)
python demo/cut-footage.py           # -> demo/video-assets/footage/*.mp4
python demo/build-video.py           # -> demo/cinemory-demo.mp4 (+ .en.srt + .beats.json)
```

Per-beat narration is cached by a hash of (text + voice + model), so tuning one
line never re-synthesizes or re-bills the others. Editing `BEATS` in
`build-video.py` regenerates the video and both sidecars together. Re-running
`cut-footage.py` after a narration edit re-cuts the clips to the new lengths;
it is only needed when a beat's narration grows **past** its clip, and the
cheap way to check is a dry run of the audio pass, which prints every beat's
measured length before a frame is rendered.

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
