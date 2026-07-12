# Cinemory — Backblaze Generative Media Hackathon submission

> Turn a set of photos into a scored, cinematic video reel — generated with
> **Genblaze**, stored on **Backblaze B2**, and sealed with verifiable SHA-256
> **provenance** on every output.

- **Repo:** https://github.com/upgradedev/cinemory (public, MIT)
- **Live app:** https://cinemory-595784992266.europe-west1.run.app
  *(working Cloud Run URL — currently in `live` mode. The deployed revision runs
  a pre-fix image whose `POST /reels` 500s without creds; the code now
  auto-degrades to the offline path in `live` mode, so a redeploy makes
  `POST /reels` return 200 with no creds — see "Honest status" below.
  `cinemory.ai` is **not yet mapped** — pending DNS; use the run.app URL for now.)*
- **Demo video:** *(owner-blocked: record ~3 min — script in [`video-script.md`](video-script.md))*
- **Deadline:** 2026-08-03 5:00pm EDT

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
- **Provider-agnostic** — swap GMI Cloud / OpenAI / Google / Runway / Luma
  without touching the pipeline.

### AI providers & models used (Devpost requirement)

| Role | Model | Provider (via Genblaze) |
|---|---|---|
| Photo → video (I2V) | `Kling-Image2Video-V2.1-Master` | GMI Cloud |
| Chapter bridge (FLF2V) | `seedance-2-0-260128` | GMI Cloud |
| Still generation (optional) | `seedream-5.0-lite` | GMI Cloud |

Models are configurable per pipeline; any Genblaze-supported provider works.

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
- **Testing pyramid, all offline (no creds):** unit → integration → e2e, plus the
  SDK-boundary Genblaze contract test — which drives a **real** Genblaze
  `Pipeline` + `ObjectStorageSink` (over an in-memory backend) so the live
  sink→store→readback→sha256-chain path is genuinely exercised, not just the
  offline fakes. **149 tests — 147 pass in CI with 2 environment-conditional
  skips** (ffmpeg and the GMICloud SDK, neither installed in CI; all 149 pass
  locally when both are present).
- **Security in CI:** gitleaks (fail-fast) · CodeQL (python + js/ts) ·
  `pip-audit --strict` · `npm audit` · ruff.
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

**Done (this submission):**
- Full offline pipeline + provenance runs for real; 149 tests (147 pass in CI +
  2 environment-conditional skips — ffmpeg / GMICloud SDK).
- Genblaze adapter **verified against the real published SDK** and contract-tested
  in CI (closes the prior "untested vs real SDK" gap).
- B2 + Genblaze usage is meaningful (both do real storage + provenance).
- Docs, Dockerfile, `.env.example`, security scans all green.

**Live deploy — deployed revision runs the pre-fix image (owner redeploy clears it):**
The Cloud Run service `cinemory` (europe-west1) **is live** at
https://cinemory-595784992266.europe-west1.run.app — it was cut over to
`CINEMORY_MODE=live` **without** B2/GMI credentials, and the *currently-deployed*
revision predates the degrade-to-offline fix, so:
- `GET /health` → `{"status":"ok","mode":"live"}` (serves)
- `POST /reels` → **HTTP 500** on that old revision (no creds present).
The **code now prevents this**: in `live` mode without creds the API degrades to
the offline path, so `POST /reels` returns 200 with a real reel + sealed
manifest. Owner-only step: **redeploy the latest image** (see
[`../deploy/CLOUDRUN.md`](../deploy/CLOUDRUN.md)) — that alone clears the 500, no
creds or mode change required; attach `GMI_API_KEY` + B2 vars only for *real*
live generation.

**Owner action (redeploy needs no creds; a real live run does):**
1. **Refresh the live deploy** — redeploy the latest image so the deployed
   revision picks up the degrade-to-offline fix (`POST /reels` → 200 without
   creds). Then optionally map `cinemory.ai` (A + AAAA DNS — see
   [`../deploy/CLOUDRUN.md`](../deploy/CLOUDRUN.md)); until mapped, the judge URL
   is the run.app link above.
2. **Live run (needs the owner's B2 + GMI credentials — cannot be faked)** — set
   `.env`, `CINEMORY_MODE=live`, run the CLI once to produce a real B2-backed
   reel. *(No live-run results are claimed here without creds.)*
3. **Record** the ~3-min demo video ([`video-script.md`](video-script.md)).
4. **Submit** the Devpost form (repo URL, app URL, models list above, this doc,
   video URL) before 2026-08-03 5:00pm EDT.
