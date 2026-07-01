# Cinemory — your memories, made into film

> Turn a set of photos into a scored, cinematic video reel — generated with
> [Genblaze](https://github.com/backblaze-labs/genblaze), stored on
> [Backblaze B2](https://www.backblaze.com/cloud-storage), and sealed with
> verifiable SHA-256 **provenance** on every output.

Built for the [Backblaze Generative Media Hackathon](https://backblaze-generative-media.devpost.com/).

---

## Origin story

Cinemory began as a personal project: a video gift, made from photos, for a
wedding anniversary — memories turned into a short film scored to music. This
repository generalizes that idea into a production-shaped generative-media app.

**Privacy first, by construction.** The original anniversary content is private
and stays private. This public repo and its demo operate on **synthetic demo
memories only** — images generated programmatically at runtime
([`synthetic.py`](src/cinemory/synthetic.py)). No real personal photo or datum
is read, generated, or committed anywhere in this project. See
[PII safety](#pii-safety).

---

## What it does

Given a set of (synthetic) memories organised into *chapters*:

1. **Photo → clip** — each photo is animated into a short video via an
   image-to-video model (Genblaze step).
2. **Chapter bridges** — first-last-frame transitions smoothly connect scenes.
3. **Music-driven cuts** — scene changes can be planned onto musical beats.
4. **Stitch** — clips are assembled into one reel (deterministic offline, or a
   real ffmpeg cinematic colour-grade).
5. **Store on B2** — every input, clip, the final reel, and the run manifest are
   written to Backblaze B2 under content-addressed keys.
6. **Provenance** — a SHA-256-sealed manifest records provider, model, prompt,
   params, timestamps and every asset hash; it is persisted to B2 *and* embedded
   into the reel container, and can be re-verified at any time.

---

## Architecture

```
                     ┌──────────────────────────────┐
  Browser client ───▶│  Cinemory API (FastAPI)       │
  (web/, TS)         │  /health · /reels · /reels/id  │
                     └───────────────┬───────────────┘
                                     │
                         ┌───────────▼────────────┐
                         │   ReelPipeline           │  orchestration
                         │   (src/cinemory/          │  (ports only —
                         │    pipeline.py)           │   provider/storage
                         └───────┬───────┬──────────┘   agnostic)
             MediaProvider port  │       │  StorageBackend port
              ┌──────────────────▼─┐   ┌─▼───────────────────────┐
   LIVE  ────▶│ Genblaze adapter    │   │ Backblaze B2 adapter     │◀──── LIVE
              │ (video/image/audio  │   │ (S3-compatible, boto3)   │
              │  providers)         │   └─────────────────────────┘
   OFFLINE ──▶│ Fake provider       │   │ Fake storage (in-memory) │◀──── OFFLINE
              │ (deterministic bytes)│  └─────────────────────────┘      (CI)
              └─────────────────────┘
                                     │
                         ┌───────────▼────────────┐
                         │  Provenance (SHA-256)    │  build · verify · embed
                         │  src/cinemory/provenance  │  — runs for REAL offline
                         └─────────────────────────┘
```

The orchestrator depends **only on ports** (`MediaProvider`, `StorageBackend`,
`Stitcher`). The real adapters wrap Genblaze and B2; the fakes implement the
same protocols with no network. The *same* pipeline code — including the real
hashing and provenance — runs in both modes, so CI is green with zero
credentials while the live path is a one-line adapter swap.

---

## How Backblaze B2 is used

- **Every artifact is persisted to B2**: synthetic input photos, each generated
  clip, chapter bridges, the final reel, the embedded-provenance reel, and the
  `manifest.json`.
- **Content-addressed layout** (`KeyStrategy.HIERARCHICAL`):
  `<reel>/<kind>/<sha2>/<sha256>/<name>` — identical bytes deduplicate by hash.
- **Data orchestration**: the storage backend keeps a queryable run index
  (JSONL catalogue of every object + size + content-type), the analogue of
  Genblaze's Parquet index sink — a catalogue you can query over your whole
  media library.
- B2 is S3-compatible, so the adapter ([`b2_storage.py`](src/cinemory/adapters/b2_storage.py))
  is a thin boto3 client; credentials come only from the environment.

## How Genblaze is used

- Generation is expressed as **Genblaze pipeline steps** (image-to-video,
  first-last-frame bridge, audio) behind the `MediaProvider` port
  ([`genblaze_provider.py`](src/cinemory/adapters/genblaze_provider.py)).
- Cinemory adopts Genblaze's signature **provenance model** as a first-class app
  feature: SHA-256 content addressing, a sealed run manifest, manifest embedding
  into the media container, and offline re-verification
  ([`provenance.py`](src/cinemory/provenance.py)).
- Provider-agnostic by design — swap GMI Cloud / OpenAI / Google / Runway / Luma
  without touching the pipeline.

### AI providers & models

| Role | Default model (via Genblaze) | Provider |
|---|---|---|
| Photo → video (I2V) | `Kling-Image2Video-V2.1-Master` | GMI Cloud |
| Chapter bridge (FLF2V) | `seedance-2-0-260128` | GMI Cloud |
| Still generation (optional) | `seedream-5.0-lite` | GMI Cloud |

Models are configurable per pipeline; any Genblaze-supported provider works.

---

## Quickstart

### Offline (no credentials — this is what CI runs)

```bash
pip install -r requirements-dev.txt
pip install -e .

# Generate a reel end-to-end from synthetic photos and verify provenance:
python -m cinemory.cli --name demo --chapters 3 --per-chapter 2 --bridges --out out

# Run the API:
uvicorn cinemory.api:app --reload
# POST http://localhost:8000/reels   {"name":"demo","chapters":3,"per_chapter":2}
```

### Live (real Genblaze + Backblaze B2)

```bash
cp .env.example .env          # fill B2 + provider credentials
pip install -e ".[live]"
export CINEMORY_MODE=live
export CINEMORY_STITCH=ffmpeg # optional real cinematic grade (needs ffmpeg)
python -m cinemory.cli --name demo --chapters 3 --per-chapter 2
```

### Docker

```bash
docker build -t cinemory .
docker run -p 8000:8000 cinemory       # offline by default
```

---

## Testing & CI

A full testing pyramid runs offline (fakes for Genblaze + B2, no creds):

| Layer | Location | Proves |
|---|---|---|
| **Unit** | `tests/unit/` | provenance hashing/verify/tamper-detection, key strategy, synthetic photos, beat-cut planning, fakes |
| **Integration** | `tests/integration/` | pipeline wiring (photos→clips→bridges→reel), FastAPI routes, real ffmpeg stitch (skipped if ffmpeg absent) |
| **E2E** | `tests/e2e/` | synthetic memories → reel → B2 → reload manifest → **assert on real SHA-256 the provenance layer recomputes** |

```bash
pytest                 # whole pyramid
pytest tests/unit      # or a single layer
```

### Security checks (all in CI, all offline)

- **gitleaks v8.18.4** — secret scan, fail-fast before build (`--redact`).
- **CodeQL** — SAST for `python` + `javascript-typescript`.
- **Dependency audit** — `pip-audit --strict` (Python) + `npm audit` (web).
- **ruff** — lint.

See [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## PII safety

This is a hard rule of the project:

- The only input source is [`synthetic.py`](src/cinemory/synthetic.py) —
  deterministic, programmatically drawn images.
- No real personal media is read, generated, or committed. The private
  anniversary content that inspired Cinemory is **not** in this repo.
- `.gitignore` blocks common photo formats, a `private/` directory, and `.env`.
- CI runs a gitleaks secret scan on every push/PR.

---

## Project layout

```
src/cinemory/
  models.py        domain types (ReelSpec, Chapter, Bridge, Asset, ...)
  ports.py         MediaProvider · StorageBackend · Stitcher protocols
  pipeline.py      ReelPipeline orchestrator
  provenance.py    SHA-256 manifest: build · verify · embed · extract
  keys.py          content-addressed key strategies (B2 layout)
  stitch.py        FakeStitcher (offline) · FfmpegStitcher (real grade)
  music.py         beat-cut planning (pure) + optional librosa analysis
  synthetic.py     PII-safe synthetic photo generation
  config.py        offline/live adapter selection
  api.py           FastAPI app
  cli.py           end-to-end CLI
  adapters/
    fake_provider.py · fake_storage.py     offline
    genblaze_provider.py · b2_storage.py   live
web/               minimal typed browser client (TS)
tests/             unit · integration · e2e
```

## License

MIT — see [LICENSE](LICENSE). Genblaze is MIT; Cinemory (the founder's own
product/brand) is reused here by concept and pattern, with synthetic data only.
