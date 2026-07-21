# Cinemory — Backblaze Generative Media Hackathon submission

> Turn a set of photos into a scored, cinematic video reel — generated with
> **Genblaze**, stored on **Backblaze B2**, and sealed with verifiable SHA-256
> **provenance** on every output.

- **Repo:** https://github.com/upgradedev/cinemory (public, MIT)
- **Live app:** https://cinemory-595784992266.europe-west1.run.app
  *(verified 2026-07-22: live env with a funded GMI account — `GET /health` →
  200 with `mode:"live"`, `provider:"genblaze"`, `storage:"B2Storage"`;
  `GET /occasions` → 200 with 6 themes; **real live generation is proven** —
  8 completed Kling renders (~242s avg), a real h264 720p 30.6s reel on B2,
  and a real upload-path generation on the live box itself. `/` serves the
  React product UI. The Firebase mirror https://upgradegr-cinemory.web.app
  serves the identical app. `cinemory.ai` is **not yet mapped** — pending DNS;
  use the run.app URL.)*
- **Demo video:** recorded + committed —
  [`demo/cinemory-demo.mp4`](cinemory-demo.mp4) (2:58, inside Devpost's 3-min
  cap). `TODO(owner): paste YouTube URL` — Devpost requires a publicly hosted
  YouTube/Vimeo/Youku link; the repo mp4 alone does not satisfy that rule.
- **Deadline:** 2026-08-03 5:00pm EDT. Per the rules the app must stay freely
  testable through **2026-08-11 5:00pm EDT** — keep the Cloud Run service up
  through judging.

---

## Devpost form — field map (copy-paste)

> **Draft filled 2026-07-21** — submission **1108702**
> (https://devpost.com/software/cinemory), DRAFT with **3/5 steps done**.
> Missing only the **Video demo link** (YouTube upload pending) and the
> owner-only T&C acceptance + final **Submit**. Gallery/thumbnail assets are
> rendered (7 PNG, 1200×800) and held outside the repo.

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
  exercised, not just the offline fakes. **Backend: 235 passed locally**
  (with the live extras); **in CI 232 passed + 3 env-gated skips** (2 gmicloud
  + 1 boto3; measured 2026-07-22). **Frontend: 31 vitest tests** (5 files,
  measured 2026-07-21).
- **Readiness gate:** `python scripts/readiness.py` scores the repo against the
  judging criteria with real-evidence checks. As of 2026-07-22: automatable
  completeness **100.0% (17/17) PASS**; full completeness **85.6%** with 3
  user-gated live items — **all three are now factually done** (live redeploy
  + live B2 objects verified 2026-07-21/22, the live Genblaze reel proven
  2026-07-22 on the funded account; see "Honest status" below). They stay
  listed only as keep-true-through-judging obligations.
- **Security in CI:** gitleaks (fail-fast) · CodeQL (python + js/ts) ·
  `pip-audit --strict` · `npm audit` · ruff · pen-test suite (`tests/security/`).
- **Deployable:** `Dockerfile` (ffmpeg included) → Cloud Run / Container Apps /
  Fly; FastAPI API (`/health`, `/occasions`, `/reels`, `/reels/upload` +
  `/reels/upload-multipart` for real photo bytes, `/reels/{name}`).
- **Never-500 core action:** in `live` mode the API uses the real Genblaze/B2
  backends only when their credentials are present, and otherwise degrades
  transparently to the offline path — so `POST /reels` always returns a real
  reel + sealed manifest (`GET /health` reports the effective backends). On top
  of that, `_run_reel()` now degrades honestly **per request**: if the live
  provider fails mid-request, the reel is re-run on the offline provider against
  the **same real storage**, the response carries `provider_degraded: true` +
  `degrade_reason: <ExceptionClass>`, and the manifest records the provider that
  actually generated the assets (an offline-path failure still 500s — no
  silent masking).
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

**Done (verified 2026-07-22) — real live generation is PROVEN:**
- **The full live chain ran for real** (funded GMI account, spend ≈$2.6):
  **8 completed Kling I2V renders** (~242s avg) + **one live seedance FLF2V
  bridge** (bridge path proven once; further bridges hit a GMI-side outage).
  The composed reel is **real h264 720p, 30.6s, byte-exact sha256
  `db6a3281…`** — re-verified from the durable B2 bytes. B2 after the run:
  **133 objects**, `index.jsonl` **174 rows**, Genblaze sink chain verified
  end-to-end.
- **The live box generated for real on the upload path too** — a
  `POST /reels/upload-multipart` on Cloud Run ran a 265s Kling render (the
  request 504'd at the old 300s Cloud Run default while the reel completed
  server-side; fixed by `--timeout 600` in this repo).
- **Same-day P0 find-fix (honest engineering):** the first funded run exposed
  four real bugs, all fixed the same day in `fix/live-run-p0s` — the 512×288
  synthetic default was under Kling's 300px minimum side (live submits failed
  `Image pixel is invalid`; default now **1024×576**, proven live); presigned
  playback URLs 401'd (client built without region + SigV4; now pinned);
  Cloud Run's 300s timeout cut off ~330–350s generations (now 600s); and
  concurrent writers clobbered `index.jsonl` rows (now merge-on-write, union
  by key). The run cost ≈$2.6 and turned every "should work" into "seen
  working" — or into a fix.

**Done earlier (verified 2026-07-21):**
- **The live-inputs fix landed** — PR #15 merged (`7b6223f`): user photos are
  hosted content-addressed under `chain-inputs/<sha256>` and attached to the
  Genblaze run via presigned `external_inputs=[Asset...]`; the seedance FLF2V
  model is routed via a ModelSpec registry override (`first_frame` /
  `last_frame`); and `_run_reel()` degrades honestly **per request** — a
  live-provider failure re-runs on the offline provider against the same real
  storage, the response carries `provider_degraded: true` +
  `degrade_reason: <ExceptionClass>`, and the manifest records the provider
  that actually generated the assets (an offline-path failure still 500s).
  +12 tests with the fix.
- **The fix is proven against live GMI** (2026-07-21, same GMI account, same
  minute): old payload → `400 image (Required parameter is missing)`; fixed
  I2V payload → `402 Insufficient credits`; fixed FLF2V → `402`. GMI validates
  the payload before billing, so the 400 is gone on **both** model paths —
  and $0.00 was consumed (GMI bills only completed requests). A sealed
  genblaze failure manifest (`genblaze/manifests/63838aad-…`) records the
  input asset (image/png, sha `b85779…`, presigned B2 URL) — the photo
  provably reached the SDK and the wire.
- **The live box runs the fixed code with full live env.** Cloud Run revision
  `cinemory-00009-cjv` runs `7b6223f`. `GET /health` on **both**
  https://cinemory-595784992266.europe-west1.run.app/health and
  https://upgradegr-cinemory.web.app/health →
  `{"status":"ok","service":"cinemory-api","mode":"live","provider":"genblaze","storage":"B2Storage"}`.
  `POST /reels` → **200** with `provider_degraded: true`,
  `degrade_reason: "PipelineError"`, sealed manifest_hash
  `b830fcd1…619d28ae`, provider honestly recorded `fake-genblaze` — the
  degrade was active **only** because the GMI account balance was then zero
  (closed 2026-07-22: account funded, real generation proven above).
- **Real B2 writes from the live box are proven** — a full object set
  (photo / clip / manifest / reel / reel.provenance) under
  `mitigation-smoke-1/` plus a growing `index.jsonl`; the bucket totals 31
  objects, including 9 under `live-degrade-proof/` and the `chain-inputs/`
  photo hosting. The earlier zero-capability B2 key is history — the
  owner-issued key is verified for Put + List.
- Full offline pipeline + provenance runs for real. Backend **216 passed
  locally** (with the gmicloud extra); **in CI 214 passed + 2 gmicloud-gated
  skips**; frontend **21 vitest tests**.
- Genblaze adapter **verified against the real published SDK** — the contract
  test passes against genblaze-core 0.3.6 (SDK line released 2026-07-17:
  genblaze 0.4.3 / core 0.3.6 / s3 0.3.5 / gmicloud 0.3.3; existing pins
  already cover them).
- B2 + Genblaze usage is meaningful (both do real storage + provenance).
- Readiness gate: automatable **100.0% (17/17) PASS**; full **85.6%** (3
  user-gated live items, of which two — live redeploy, live B2 objects — are
  now factually done; see above).
- Demo video recorded + committed (`demo/cinemory-demo.mp4`, 2:58).
- **Devpost draft filled** — submission 1108702
  (https://devpost.com/software/cinemory), DRAFT with 3/5 steps done; gallery
  + thumbnail assets rendered (held outside the repo).
- Docs, Dockerfile, `.env.example`, security scans all green.

**The GMI-credits blocker is CLOSED (2026-07-22)** — the account was funded
and real live generation is proven (see above). Nothing code-side remains.

**Owner checklist — ONLY these three remain (in order):**
1. **Upload the demo video to YouTube** (public or unlisted) and paste the URL
   into the Devpost "Video demo link" field and this doc. Devpost requires a
   publicly hosted YouTube/Vimeo/Youku link; the repo mp4 does not satisfy it.
2. **Add the gallery images** (the 7 rendered 1200×800 PNGs, held outside the
   repo) to the Devpost form.
3. **Accept the T&C and Submit the project on Devpost** — the draft is already
   filled (field map at the top of this doc). Deadline 2026-08-03 5:00pm EDT.

Housekeeping after this PR merges: one Cloud Run redeploy to pick up the P0
fixes (1024×576 synth default, presign region/SigV4, `--timeout 600`), then
keep the app up through **2026-08-11 5:00pm EDT** — the rules require the app
to stay freely testable through judging.
