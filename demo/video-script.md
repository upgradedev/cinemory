# Cinemory — demo video

`cinemory-demo.mp4` is a **2:17**, narrated walkthrough of the current app. It is
built beat-by-beat so the picture and the voice can never drift apart, and a CI
gate (`scripts/check_video.py`) fails the build if they do.

- **Voice:** ElevenLabs, voice `pNInz6obpgDQGcFmaJgB`, model `eleven_multilingual_v2`
  (the same clear, professional voice our other project demos use).
- **Picture:** real, on-brand stills only — the six finished gallery cards under
  `video-assets/cards/` and three frames pulled straight from a real live
  generation run under `video-assets/frames/`. A gentle Ken Burns move on each,
  with a burned-in caption. No fabricated UI.
- **Sidecars (committed):** `cinemory-demo.en.srt` (full narration, per-beat
  windows) and `cinemory-demo.beats.json` (the machine-readable beat script and
  the single source of truth the gate checks against).

## Beats

| # | Beat | Picture | The line, in short |
|---|------|---------|--------------------|
| 1 | Hook | thumbnail card | Your memories, made into film — and sealed so anyone can prove it's real. |
| 2 | The trust problem | real generated frame | Generative video is easy to make and hard to trust; which model, which photos, and was any frame changed. |
| 3 | What it does | pipeline card | Photos plus an occasion return a scored reel, content-addressed on B2 and SHA-256 sealed. |
| 4 | The reel plays | two real Kling frames | Four steps — photos, occasion, generate, play — real clips bridged and graded into one film. |
| 5 | Provenance + Verify | provenance card | Open Provenance, press Verify; the browser recomputes the SHA-256 and the seal flips to Verified, plus a server re-check. |
| 6 | What keeps it honest | B2 objects card | Every clip cites its source photo by hash; change a byte and the seal breaks; live failures degrade in the open. |
| 7 | The stack | architecture card | One core, three ports: Genblaze (Kling/seedance via GMI Cloud), Backblaze B2, FastAPI + React on Cloud Run, offline fakes in CI. |
| 8 | Close | live-proof card | Live on Cloud Run, mirrored on Firebase, open source. |

The exact spoken text for every beat lives in `cinemory-demo.beats.json` and
`cinemory-demo.en.srt`.

## Rebuilding

```bash
pip install pillow                 # plus ffmpeg/ffprobe on PATH
export ELEVENLABS_API_KEY=...       # required; the build STOPS if it is missing
python demo/build-video.py          # -> demo/cinemory-demo.mp4 (+ .en.srt + .beats.json)
```

Per-beat narration is cached by a hash of (text + voice + model), so tuning one
line never re-synthesizes or re-bills the others. Editing `BEATS` in
`build-video.py` regenerates the video and both sidecars together.

## The sync gate (CI)

`python scripts/check_video.py` ffprobes the committed mp4 and cross-checks it
against the beat script. It fails the build when the video is over the 180s hard
cap, is not H.264/yuv420p 1280x720 ~30fps with a single AAC track, or when the
SRT cues do not match the beats one-for-one in order, timing and text. It needs
only ffprobe and the standard library, and runs as the `demo-video` CI job.

## The one remaining manual step

Upload `cinemory-demo.mp4` to YouTube (unlisted or public) and paste the URL into
the Devpost submission and `demo/SUBMISSION.md`.
