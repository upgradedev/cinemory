# Cinemory — submission state

_Last updated: 2026-07-21. Deadline: 2026-08-03 5:00pm EDT. $10k. Greece-eligible._

## 2026-07-21 (late) — live chain + fix

> Supersedes the earlier same-day entry below: the B2-key blocker is
> **resolved** (owner-issued key verified Put + List), the live-mode redeploy
> is **done**, and the only remaining blocker for real live generation is a
> GMI credits top-up.

- **Bug found by the first real live run:** with a working B2 key and live
  env, the first live `POST /reels` exposed that photo inputs never reached
  the Genblaze pipeline — GMI rejected the run with
  `400 image (Required parameter is missing)`.
- **Fix: PR #15 merged (`7b6223f`)** — photos are hosted content-addressed
  under `chain-inputs/<sha256>` and attached via presigned
  `external_inputs=[Asset...]`; seedance FLF2V routed via a ModelSpec registry
  override (`first_frame`/`last_frame`); honest per-request degrade in
  `_run_reel()` (live-provider failure → offline provider + same real
  storage, response `provider_degraded: true` + `degrade_reason:
  <ExceptionClass>`, manifest records the actual provider; offline-path
  failure still 500s). **+12 tests**; backend now **216 passed locally**
  (gmicloud extra) / **214 passed + 2 gmicloud-gated skips in CI**; frontend
  21 vitest unchanged.
- **A/B/C proof against live GMI** (same account, same minute): old payload →
  `400 image (Required parameter is missing)`; fixed I2V payload →
  `402 Insufficient credits`; fixed FLF2V → `402`. GMI validates the payload
  before billing, so the 400 is gone on both model paths; **$0.00 consumed**
  (GMI bills only completed requests). A sealed genblaze failure manifest
  (`genblaze/manifests/63838aad-…`) records the input asset (image/png, sha
  `b85779…`, presigned B2 URL) — the photo provably reached the SDK and the
  wire.
- **Deploy history (today):** rev **00007** (live env, exposed the 500) →
  rev **00008** (mitigation: live-no-GMI, 200s) → rev **00009-cjv** (fixed
  code `7b6223f`, full live env — **current**).
- **Current health + smoke (verified 2026-07-21):** `GET /health` on both
  https://cinemory-595784992266.europe-west1.run.app/health and
  https://upgradegr-cinemory.web.app/health →
  `{"status":"ok","service":"cinemory-api","mode":"live","provider":"genblaze","storage":"B2Storage"}`.
  `POST /reels` → **200** with `provider_degraded: true`, `degrade_reason:
  "PipelineError"`, sealed manifest_hash `b830fcd1…619d28ae`, provider
  honestly recorded `fake-genblaze` (degrade active only because the GMI
  balance is zero).
- **B2 evidence:** real writes from the live box — full object set
  (photo/clip/manifest/reel/reel.provenance) under `mitigation-smoke-1/` +
  growing `index.jsonl`; bucket total **31 objects** incl. 9 under
  `live-degrade-proof/` + `chain-inputs/`. Key history: the earlier key had
  zero capabilities (AccessDenied); the owner-issued key verified Put + List
  today.
- **Devpost:** draft filled 2026-07-21 — submission **1108702**
  (https://devpost.com/software/cinemory), DRAFT, **3/5 steps**; missing only
  the Video demo link (YouTube upload pending) + owner T&C/Submit. Gallery +
  thumbnail assets rendered (7 PNG 1200×800, held outside the repo).
- **Remaining (owner):** 1) GMI credits top-up → one real live reel
  (`CINEMORY_MODE=live bash demo/capture-demo.sh` — expected to pass
  unchanged; **no redeploy needed**); 2) YouTube upload → paste URL into
  Devpost + `SUBMISSION.md`; 3) T&C + Submit on Devpost; 4) keep the app up
  through 2026-08-11 5:00pm EDT.

## 2026-07-21 update — SDK re-verified · live box re-verified · B2 key probed

- **Genblaze SDK resolve (all released 2026-07-17):** genblaze **0.4.3**,
  genblaze-core **0.3.6**, genblaze-s3 **0.3.5**, gmicloud **0.3.3**. The SDK
  contract test passes against core 0.3.6 (verified locally today). The
  existing pins (`genblaze-core>=0.3.4,<0.4` in requirements-dev;
  `genblaze[gmicloud]>=0.4,<0.5` in the `[live]` extra) already cover these —
  no pin change needed or made.
- **Measured tests (fresh venv, genblaze-core 0.3.6, re-measured 2026-07-21
  after the playback/honesty PR):** backend **226 collected → 224 passed,
  2 gmicloud-gated skips** (226 pass with the gmicloud extra); frontend
  **31 vitest tests** (5 files).
- **Readiness gate:** automatable **100.0% (17/17) PASS**; full **85.6%** — 3
  user-gated live items remain (`production.live_redeploy`,
  `b2.live_objects_written`, `genblaze.live_reel_generated`).
- **Live box (Cloud Run), verified today:** `GET /health` → 200 in honest
  offline-degrade mode
  (`{"mode":"offline","provider":"fake-genblaze","storage":"FakeStorage"}`);
  `GET /occasions` → 200 (6 themes); `POST /reels` → **200** with a sealed
  reel + provenance manifest; `/` serves the React UI. Firebase mirror
  https://upgradegr-cinemory.web.app identical.
- **B2 key probe:** the configured application key authenticates but has
  **capabilities=[] (zero)** — PutObject AND ListObjectsV2 return
  `AccessDenied: not entitled`. Endpoint (`s3.eu-central-003.backblazeb2.com`)
  and bucket (`cinemory`) are correct. **A new write-entitled key is pending
  from the owner**; the live run and the live-mode redeploy are gated on it.
- **Remaining checklist (in order):**
  1. Upload `demo/cinemory-demo.mp4` (2:58) to YouTube; paste the URL into
     `SUBMISSION.md` + the Devpost form (repo mp4 alone does not satisfy
     Devpost's hosted-video rule).
  2. New write-entitled B2 key → one real live run.
  3. Live-mode redeploy of Cloud Run with the credentials.
  4. Devpost form before **2026-08-03 5:00pm EDT**; keep the app freely
     testable through **2026-08-11 5:00pm EDT**.

## Where it stands: ~92/100 (code/docs complete; live-run + video are owner-only)

> ✅ **Live deploy state (2026-07-12, reconcile with `/health`):** the Cloud Run
> service `cinemory` (europe-west1) is live at
> https://cinemory-595784992266.europe-west1.run.app and **the `POST /reels` 500
> is fixed** — the latest image is deployed and `GET /health` now reports the
> effective backends (`{"mode":"offline","provider":"fake-genblaze","storage":"FakeStorage"}`),
> `POST /reels` returns **200** with a real deterministic reel + sealed manifest,
> and `/` serves the **React product UI** (no longer the legacy `web/` client).
> The redeploy path is `bash deploy/deploy-cloudrun.sh` (see
> `deploy/CLOUDRUN.md`). To get *real* live generation, redeploy with
> `CINEMORY_MODE=live` + valid `GMI_API_KEY` + B2 vars whose key is **entitled to
> PutObject** on the bucket (a key without write entitlement makes the real path
> return `AccessDenied`; the credential-free path always degrades to a 200).
> The Firebase Hosting site https://upgradegr-cinemory.web.app also serves the
> React product UI. `cinemory.ai` is **not yet mapped**; the judge URL is the
> run.app / web.app link. See `deploy/DEPLOYED.md` + `demo/SUBMISSION.md`.

The former 95-blocker — "Genblaze adapter untested vs the real SDK" — is **closed**:
the adapter is verified against the real published Genblaze SDK and contract-tested
in CI. See `feat/genblaze-adapter-contract` (PR).

### Scorecard vs the 4 Devpost criteria
| Criterion | Before | After | Note |
|---|---|---|---|
| Real-World Utility | 8.5/10 | 8.5/10 | consumer + B2B event wedge; unchanged |
| Production Readiness | 8/10 | 9/10 | +SDK contract test; 226 backend tests (224 passed + 2 gmicloud-gated skips, measured 2026-07-21) + 31 frontend; credential-free live-degrade + real-photo ingest; playable reels via the stable `/reels/{name}/video` route; drift guarded |
| B2 Storage & Orchestration | 8.5/10 | 9/10 | two real B2 write paths (Genblaze sink + cinemory) + a real queryable `index.jsonl` run index on both fake and B2 adapters |
| Use of Genblaze | 6/10 | 8.5/10 | load-bearing (gen+sink+manifest); sink→store→readback path covered offline, SDK-verified |

> **B2 run-index note:** `B2Storage` now keeps a durable `index.jsonl` catalogue
> (per-put write + query-time reload), so `GET /reels/{name}` / the ProvenancePanel
> work in live mode. It is **code-complete and unit-tested** (multi-instance,
> prefixed); it is **not yet exercised against real B2** — the live box currently
> runs the offline-degrade path because the B2 key in the deploy env is not
> entitled for `PutObject`. A write-entitled key closes that last gap.

A demo video is now committed (`demo/cinemory-demo.mp4`, ~3 min, offline-honest).
Ceiling to 95+ is gated on a write-entitled B2 key + a live-B2 run + hosting the
video.

## Verified against the real SDK
_(originally against genblaze-core 0.3.4 / -s3 0.3.4 / -gmicloud 0.3.2;
re-verified 2026-07-21 against core 0.3.6 / -s3 0.3.5 / -gmicloud 0.3.3 —
same contract, no adapter change needed)_
- `Pipeline().step(provider, model=, prompt=, modality=, **params).run(sink=, timeout=, raise_on_failure=True)` ✓
- `PipelineResult(run, manifest)`; `result.run.steps[-1].assets[0]` ✓
- `Asset` is **URL-addressed** (`url`/`sha256`/`size_bytes`/`media_type`) — no `.read()/.bytes` (old adapter bug, fixed) ✓
- `S3StorageBackend.for_backblaze(bucket, region=, key_id=, app_key=)` reads `B2_BUCKET/B2_REGION/B2_KEY_ID/B2_APP_KEY` ✓
- `ObjectStorageSink(backend, ...)`, `KeyStrategy.{HIERARCHICAL,CONTENT_ADDRESSABLE}` ✓
- `genblaze_gmicloud.GMICloud{Video,Image,Audio}Provider` ✓
- `manifest.verify_hash()` ✓

## Owner action list (all require the owner's own credentials — cannot be faked)
1. Provide `GMI_API_KEY` (GMI Cloud gives first ~270 credits free). **B2 needs no
   `.env` editing** if your canonical Backblaze vars are already exported —
   `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`, `B2_S3_ENDPOINT`
   are resolved out-of-the-box (region is derived from the endpoint; the legacy
   `B2_KEY_ID`/`B2_APP_KEY`/`B2_ENDPOINT_URL`/`B2_REGION` names still work too).
2. `pip install -e ".[live]"` then `CINEMORY_MODE=live bash demo/capture-demo.sh` — one live reel to B2.
3. Refresh the live Cloud Run revision: **redeploy the latest image** — the code
   now auto-degrades, so this alone makes `POST /reels` return 200 (no creds
   needed to clear the old revision's 500). Attach `GMI_API_KEY` + B2 vars only
   to get *real* live generation. Then optionally map **cinemory.ai** (not yet
   mapped); until then the judge URL is the run.app link.
4. Record the ~3-min video (`demo/video-script.md`).
5. Submit the Devpost form (see `demo/SUBMISSION.md` for every field, incl. model list).

## Premium React frontend (2026-07-04)

A flagship cinematic web client now lives in `frontend/` (Vite · React 18 ·
TypeScript strict · Tailwind · shadcn-style UI · React Query · Zod · Zustand ·
framer-motion). It **replaces the bare `web/` SPA as the product UI** — a
four-step wizard (Photos → Occasion → Generate → Result + Provenance) with a
dark filmic aesthetic, full loading/empty/error/success states, responsive +
accessible, and the complete share feature set preserved.

- The Cloud Run container now serves the **React client too**: the Dockerfile
  builds `frontend/` (Vite) into the image's static dir, so the API + the premium
  UI ship in one container. `web/` is **kept** as the legacy/reference SPA (still
  type-checked, built and audited by the CI `web` job) but is no longer served by
  the container. Firebase Hosting also serves the React client and rewrites the
  API routes (`/health`, `/occasions`, `/reels/**`) to Cloud Run `cinemory`
  (europe-west1) — single origin, no CORS.
- Deploy: `cd frontend && npm run build` → `firebase login` (interactive) →
  `firebase use upgradegr-cinemory` → `firebase deploy --only hosting`. Config in
  repo-root `firebase.json` + `.firebaserc`; details in `frontend/README.md`.
- CI: new `frontend` job (typecheck + vitest + build). 21 frontend tests green;
  `npm run build` clean.

## No live-run results are claimed anywhere without credentials.
