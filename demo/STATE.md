# Cinemory — submission state

_Last updated: 2026-07-04. Deadline: 2026-08-03 5:00pm EDT. $10k. Greece-eligible._

## Where it stands: ~92/100 (code/docs complete; live-run + video are owner-only)

> ⚠️ **Live deploy state (reconcile with `/health`):** the Cloud Run service
> `cinemory` (europe-west1) **is live** at
> https://cinemory-595784992266.europe-west1.run.app but was cut over to
> `CINEMORY_MODE=live` **without credentials** — `GET /health` reports
> `mode:"live"`, and `POST /reels` currently returns **HTTP 500** (core generate
> action fails, no B2/GMI creds). Owner-only fix: attach creds + redeploy, **or**
> revert the revision to `offline`. `cinemory.ai` is **not yet mapped** (HTTP 000);
> the judge URL is the run.app link. See `deploy/DEPLOYED.md` + `demo/SUBMISSION.md`.

The former 95-blocker — "Genblaze adapter untested vs the real SDK" — is **closed**:
the adapter is verified against the real published Genblaze SDK and contract-tested
in CI. See `feat/genblaze-adapter-contract` (PR).

### Scorecard vs the 4 Devpost criteria
| Criterion | Before | After | Note |
|---|---|---|---|
| Real-World Utility | 8.5/10 | 8.5/10 | consumer + B2B event wedge; unchanged |
| Production Readiness | 8/10 | 9/10 | +SDK contract test; 68 tests; drift guarded |
| B2 Storage & Orchestration | 8.5/10 | 9/10 | two real B2 write paths (Genblaze sink + cinemory) |
| Use of Genblaze | 6/10 | 8.5/10 | load-bearing (gen+sink+manifest); sink→store→readback path covered offline, SDK-verified |

Ceiling to 95+ is gated on the live app URL + demo video, which need credentials.

## Verified against the real SDK (genblaze-core 0.3.4 / -s3 0.3.4 / -gmicloud 0.3.2)
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
3. Fix the live Cloud Run revision (now `mode:live` but `POST /reels` 500s):
   attach `GMI_API_KEY` + B2 vars and redeploy, **or** revert to `offline`. Then
   optionally map **cinemory.ai** (not yet mapped); until then the judge URL is
   the run.app link.
4. Record the ~3-min video (`demo/video-script.md`).
5. Submit the Devpost form (see `demo/SUBMISSION.md` for every field, incl. model list).

## Premium React frontend (2026-07-04)

A flagship cinematic web client now lives in `frontend/` (Vite · React 18 ·
TypeScript strict · Tailwind · shadcn-style UI · React Query · Zod · Zustand ·
framer-motion). It **replaces the bare `web/` SPA as the product UI** — a
four-step wizard (Photos → Occasion → Generate → Result + Provenance) with a
dark filmic aesthetic, full loading/empty/error/success states, responsive +
accessible, and the complete share feature set preserved.

- `web/` is **kept** so the existing Dockerfile / Cloud Run container still serves
  a working UI + API (zero risk to the live deploy). Firebase Hosting now serves
  the React client and rewrites the API routes (`/health`, `/occasions`,
  `/reels/**`) to Cloud Run `cinemory` (europe-west1) — single origin, no CORS.
- Deploy: `cd frontend && npm run build` → `firebase login` (interactive) →
  `firebase use upgradegr-cinemory` → `firebase deploy --only hosting`. Config in
  repo-root `firebase.json` + `.firebaserc`; details in `frontend/README.md`.
- CI: new `frontend` job (typecheck + vitest + build). 19 frontend tests green;
  `npm run build` clean.

## No live-run results are claimed anywhere without credentials.
