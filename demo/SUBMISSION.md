# Cinemory — Backblaze Generative Media Hackathon submission

> Turn a set of photos into a scored, cinematic video reel — generated with
> **Genblaze**, stored on **Backblaze B2**, and sealed with verifiable SHA-256
> **provenance** on every output.

- **Repo:** https://github.com/upgradedev/cinemory (public, MIT)
- **Live app:** https://cinemory-595784992266.europe-west1.run.app
  *(verified 2026-07-21: `GET /health` → 200 with the effective backends
  reported — `mode:"offline"`, `provider:"fake-genblaze"`, `storage:"FakeStorage"`;
  `GET /occasions` → 200 with 6 themes; `POST /reels` → **200** with a sealed
  reel + provenance manifest; `/` serves the React product UI. The Firebase
  mirror https://upgradegr-cinemory.web.app serves the identical app.
  `cinemory.ai` is **not yet mapped** — pending DNS; use the run.app URL.)*
- **Demo video:** recorded + committed —
  [`demo/cinemory-demo.mp4`](cinemory-demo.mp4) (2:58, inside Devpost's 3-min
  cap). `TODO(owner): paste YouTube URL` — Devpost requires a publicly hosted
  YouTube/Vimeo/Youku link; the repo mp4 alone does not satisfy that rule.
- **Deadline:** 2026-08-03 5:00pm EDT. Per the rules the app must stay freely
  testable through **2026-08-11 5:00pm EDT** — keep the Cloud Run service up
  through judging.

---

## Devpost form — field map (copy-paste)

| Devpost field | Source |
|---|---|
| Project name | **Cinemory** |
| Elevator pitch / tagline | *Turn a set of photos into a scored, cinematic video reel — generated with Genblaze, stored on Backblaze B2, sealed with verifiable SHA-256 provenance.* |
| About — inspiration | section "Inspiration / Why" below |
| About — what it does | section "What it does" below |
| About — how we built it | section "How we built it" below |
| B2 usage | section "How Backblaze B2 is used" below |
| Genblaze usage + AI models | section "How Genblaze is used" + models table below |
| Built with | python · fastapi · react · typescript · genblaze · backblaze-b2 · gmi-cloud · ffmpeg · cloud-run · firebase-hosting |
| Try it out links | repo + live app + mirror (top of this doc) |
| Video URL | `TODO(owner): paste YouTube URL` |

---

## What it does (Devpost: "What it does")

Cinemory turns a set of photos, organised into *chapters*, into one short
cinematic film:

1. **Photo → clip** — each photo is animated into a short video via an
   image-to-video model (a Genblaze pipeline step).
2. **Chapter bridges** — first-last-frame transitions smoothly connect scenes.
3. **Music-driven cuts** — scene changes are planned onto musical beats.
4. **Stitch** — clips assemble into one reel (deterministic offline, or a real
   ffmpeg cinematic colour-grade).
5. **Store on B2** — every input, clip, bridge, the final reel and the run
   manifest are written to Backblaze B2 under content-addressed keys.
6. **Provenance** — a SHA-256-sealed manifest records provider, model, prompt,
   params, timestamps and every asset hash; it is persisted to B2 *and* embedded
   into the reel container, and re-verifiable offline at any time.

It began as a personal anniversary gift — photos turned into a scored short
film. This repo generalises that into a production-shaped app. **The original
personal content stays private; the public repo and demo run on synthetic photos
only** (deterministic, generated at runtime — no real photo or datum is read,
generated, or committed).

## Inspiration / Why (Devpost: "Inspiration")

Generative media is easy to make and hard to *trust*. The moment a reel is
AI-assembled from many models, three questions matter to any real audience —
consumers and, especially, brand/comms teams: *what made this, from what inputs,
and can I prove it wasn't tampered with?* Cinemory's answer is provenance as a
first-class output, not an afterthought — which is exactly what Genblaze and B2
make cheap to do right.

## How we built it (Devpost: "How we built it")

Ports and adapters, offline-first. The orchestrator (`ReelPipeline`) depends
only on three protocols: `MediaProvider`, `StorageBackend`, `Stitcher`. The
live adapters wrap a real Genblaze `Pipeline` (with Genblaze's own
`ObjectStorageSink` writing to B2) and a boto3 B2 client. The offline fakes
implement the same protocols deterministically, so the *same* pipeline code —
including the real SHA-256 provenance — runs in CI with zero credentials. A
FastAPI app exposes it; a React (Vite + TypeScript) frontend ships in the same
container on Cloud Run, mirrored on Firebase Hosting. In `live` mode each
backend is used only when its credentials are present; otherwise the API
degrades transparently to the offline path, so the core action never 500s.
The Genblaze adapter is contract-tested against the real published SDK in CI,
so API drift fails the build instead of failing the demo.

---

## How Backblaze B2 is used (criterion 3: B2 Storage & Data Orchestration)

- **Every artifact is persisted to B2** — synthetic input photos, each generated
  clip, chapter bridges, the final reel, the embedded-provenance reel, and
  `manifest.json`. A 3-chapter demo writes **17 objects**.
- **Content-addressed layout** (`<reel>/<kind>/<sha2>/<sha256>/<name>`) — identical
  bytes deduplicate by hash ([`keys.py`](../src/cinemory/keys.py)).
- **Data orchestration** — the storage backend keeps a queryable JSONL run index
  (every object + size + content-type), the analogue of Genblaze's Parquet index
  sink: a catalogue you can query across your whole media library.
- **Two B2 write paths, both real:**
  - Genblaze's own `ObjectStorageSink` over `genblaze_s3.S3StorageBackend.for_backblaze(...)`
    persists every *generated asset* + its manifest to B2 (criterion 4 below).
  - Cinemory's boto3 adapter ([`b2_storage.py`](../src/cinemory/adapters/b2_storage.py))
    persists the *composed reel* + reel-level manifest to B2.
- B2 is S3-compatible; credentials come only from the environment.

## How Genblaze is used (criterion 4: Use of Genblaze)

Genblaze is **load-bearing**, not a byte source we throw away:

- **Generation** is a real Genblaze `Pipeline` step —
  `Pipeline("cinemory-step").step(provider, model=, prompt=, modality=).run(sink=…, raise_on_failure=True)`
  — behind the `MediaProvider` port ([`genblaze_provider.py`](../src/cinemory/adapters/genblaze_provider.py)).
- **Genblaze owns per-asset storage + provenance:** the adapter attaches
  Genblaze's `ObjectStorageSink`, so Genblaze content-addresses the output,
  persists it to B2, and **seals a SHA-256 provenance manifest** for the run
  (`result.manifest.verify_hash()`).
- **Provenance chaining:** Cinemory reads the durable bytes back through the same
  backend, **verifies them against Genblaze's sealed SHA-256**, and folds that
  hash into its own reel-level manifest. Genblaze owns per-asset provenance;
  Cinemory owns composed-reel provenance.
- **Verified against the real SDK.** Every Genblaze call and result shape is
  contract-tested against the *actual published SDK* using its own shipped mock
  provider (`genblaze_core.testing`) —
  [`tests/integration/test_genblaze_contract.py`](../tests/integration/test_genblaze_contract.py).
  API drift fails CI. `genblaze-core` is installed in CI (pure-Python, no creds).
- **Provider port; GMI Cloud live today** — generation sits behind the
  `MediaProvider` port. Live generation currently supports the **GMI Cloud**
  provider via Genblaze; other Genblaze providers (OpenAI, Google, Runway,
  Luma) are scaffolded in config and on the roadmap — the port design lets
  them slot in without touching the pipeline.

### AI providers & models used (Devpost requirement)

| Role | Model | Provider (via Genblaze) |
|---|---|---|
| Photo → video (I2V) | `Kling-Image2Video-V2.1-Master` | GMI Cloud |
| Chapter bridge (FLF2V) | `seedance-2-0-260128` | GMI Cloud |
| Still generation (optional) | `seedream-5.0-lite` | GMI Cloud |

Models are configurable per pipeline. Live generation currently runs through
GMI Cloud; further Genblaze providers are on the roadmap.

---

## Real-world utility (criterion 1)

- **Consumer:** memory films for anniversaries, graduations, weddings,
  year-in-review — the origin use case, real and repeatable.
- **B2B wedge:** conferences, award ceremonies and sales kick-offs generate large
  photo volumes a comms team must turn into a branded highlight reel *fast, with
  clear rights/provenance*. Six config-driven occasion themes (incl.
  `business-event/award-ceremony`) + LinkedIn share + provenance target exactly
  this recurring, budgeted need. See [`ROADMAP.md`](../ROADMAP.md).

## Production readiness (criterion 2)

- **Ports + adapters** — orchestration depends only on `MediaProvider` /
  `StorageBackend` / `Stitcher` protocols; live↔offline is a one-line swap.
- **Testing pyramid, all offline (no creds):** unit → integration → e2e →
  pen-test, plus the SDK-boundary Genblaze contract test — which drives a
  **real** Genblaze `Pipeline` + `ObjectStorageSink` (over an in-memory
  backend) so the live sink→store→readback→sha256-chain path is genuinely
  exercised, not just the offline fakes. **Backend: 204 tests — 203 passed,
  1 environment-conditional skip** (measured 2026-07-21, fresh venv,
  genblaze-core 0.3.6). **Frontend: 21 vitest tests** (4 files).
- **Readiness gate:** `python scripts/readiness.py` scores the repo against the
  judging criteria with real-evidence checks. As of 2026-07-21: automatable
  completeness **100.0% (17/17) PASS**; full completeness **85.6%** with 3
  user-gated live-credential items (live redeploy, live B2 objects written,
  live Genblaze reel).
- **Security in CI:** gitleaks (fail-fast) · CodeQL (python + js/ts) ·
  `pip-audit --strict` · `npm audit` · ruff · pen-test suite (`tests/security/`).
- **Deployable:** `Dockerfile` (ffmpeg included) → Cloud Run / Container Apps /
  Fly; FastAPI API (`/health`, `/occasions`, `/reels`, `/reels/upload` +
  `/reels/upload-multipart` for real photo bytes, `/reels/{name}`).
- **Never-500 core action:** in `live` mode the API uses the real Genblaze/B2
  backends only when their credentials are present, and otherwise degrades
  transparently to the offline path — so `POST /reels` always returns a real
  reel + sealed manifest (`GET /health` reports the effective backends).
- **PII-safe by construction** — only synthetic inputs; `.gitignore` blocks
  photos/`private/`/`.env`; secret scan on every push.

---

## Try it out (Devpost: "How to run" / setup instructions)

### Offline (no credentials — what CI runs, judges can run in <1 min)

```bash
pip install -r requirements-dev.txt && pip install -e .
python -m cinemory.cli --name demo --chapters 3 --per-chapter 2 --bridges --out out
# → real reel.mp4 + manifest.json + provenance-embedded reel;
#   prints: verify manifest: True / verify asset: True / verify embedded: True
```

### Live (real Genblaze + Backblaze B2)

```bash
cp .env.example .env          # fill B2 (B2_BUCKET_NAME/_REGION/_KEY_ID/_APP_KEY) + GMI_API_KEY
pip install -e ".[live]"
export CINEMORY_MODE=live CINEMORY_STITCH=ffmpeg
python -m cinemory.cli --name demo --chapters 3 --per-chapter 2 --bridges
```

---

## Honest status — what is done vs owner-blocked

**Done (verified 2026-07-21):**
- **Live box healthy, honest offline-degrade mode.** The Cloud Run service
  `cinemory` (europe-west1) serves at
  https://cinemory-595784992266.europe-west1.run.app: `GET /health` → 200
  reporting the effective backends (`mode:"offline"`,
  `provider:"fake-genblaze"`, `storage:"FakeStorage"`), `GET /occasions` → 200
  (6 themes), `POST /reels` → **200** with a sealed reel + provenance
  manifest, `/` serves the React product UI. The Firebase mirror
  https://upgradegr-cinemory.web.app is identical.
- Full offline pipeline + provenance runs for real. Backend **204 tests → 203
  passed + 1 skipped** (fresh venv, genblaze-core 0.3.6); frontend **21
  vitest tests**.
- Genblaze adapter **verified against the real published SDK** — the contract
  test passes against genblaze-core 0.3.6 (SDK line released 2026-07-17:
  genblaze 0.4.3 / core 0.3.6 / s3 0.3.5 / gmicloud 0.3.3; existing pins
  already cover them).
- B2 + Genblaze usage is meaningful (both do real storage + provenance).
- Readiness gate: automatable **100.0% (17/17) PASS**; full **85.6%** (3
  user-gated live items).
- Demo video recorded + committed (`demo/cinemory-demo.mp4`, 2:58).
- Docs, Dockerfile, `.env.example`, security scans all green.

**Blocked on a write-entitled B2 key (owner):**
The configured B2 application key authenticates but carries **zero
capabilities** — PutObject and ListObjectsV2 both return
`AccessDenied: not entitled` (probed 2026-07-21). The endpoint
(`s3.eu-central-003.backblazeb2.com`) and bucket (`cinemory`) are correct; the
key itself lacks entitlements. A new write-entitled key is pending from the
owner. The real live run and the live-mode redeploy are gated on it.

**Owner checklist (in order):**
1. **Upload the demo video to YouTube** (public or unlisted) and paste the URL
   into this doc and the Devpost form. Devpost requires a publicly hosted
   YouTube/Vimeo/Youku link; the repo mp4 does not satisfy it.
2. **Create a write-entitled B2 application key**, then run one real live reel
   (`CINEMORY_MODE=live` + `GMI_API_KEY` + the B2 vars). *(No live-run results
   are claimed here until that happens.)*
3. **Redeploy Cloud Run in live mode** with those credentials (see
   [`../deploy/CLOUDRUN.md`](../deploy/CLOUDRUN.md)). Optionally map
   `cinemory.ai`; until mapped, the judge URL is the run.app link above.
4. **Submit the Devpost form** (field map at the top of this doc) before
   2026-08-03 5:00pm EDT — then keep the app freely testable through
   **2026-08-11 5:00pm EDT**.
