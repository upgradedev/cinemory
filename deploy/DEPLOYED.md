# Cinemory — deploy record

## 2026-07-04 — first Cloud Run deploy (OFFLINE, validated)

| | |
|---|---|
| Project | `upgradegr-cinemory` (billing `01A97A-55FE41-BC2FC8`) |
| Region | `europe-west1` |
| Service | `cinemory` |
| Revision | `cinemory-00002-nnj` (reproducible clean-git build) |
| Image | `europe-west1-docker.pkg.dev/upgradegr-cinemory/cinemory/cinemory:20260704-180155-clean` |
| Built from | git `7cb94a5` on `feat/cloud-run-deploy` — **image == PR #3** (no local WIP) |
| Mode | `offline` (CINEMORY_MODE=offline, CINEMORY_STITCH=fake) — zero credentials |
| Auth | public (`--allow-unauthenticated`) |
| **URL** | **https://cinemory-595784992266.europe-west1.run.app** |

Built via Cloud Build (no local Docker). Verified serving:

- `GET /health` → `{"status":"ok","mode":"offline"}`
- `GET /occasions` → occasion presets
- `POST /reels` → full offline pipeline, returns manifest hash + 6 steps
- `GET /` → 200 `text/html` (web client)
- `GET /dist/main.js` → 200 `application/javascript`
- `GET /dist/lib/api.js` → 200

> Historical record for that revision, which served the legacy `web/` (tsc) SPA.
> The image later switched to building the `frontend/` React (Vite) client, whose
> bundle is served under `/assets/*` — see `deploy/CLOUDRUN.md`.

## ✅ Current live state — verified 2026-07-21 (LIVE mode, rev `cinemory-00009-cjv`)

Cloud Run revision **`cinemory-00009-cjv`** runs **`7b6223f`** (PR #15 —
live-inputs fix + honest per-request degrade) with the **full live env**
(`CINEMORY_MODE=live` + owner-issued B2 key + `GMI_API_KEY`). Verified against
the live service on 2026-07-21:

- `GET /health` → 200 on **both**
  https://cinemory-595784992266.europe-west1.run.app/health and
  https://upgradegr-cinemory.web.app/health:
  `{"status":"ok","service":"cinemory-api","mode":"live","provider":"genblaze","storage":"B2Storage"}`
- `POST /reels` → **200** with `provider_degraded: true`,
  `degrade_reason: "PipelineError"`, sealed manifest_hash
  `b830fcd1…619d28ae`, provider honestly recorded `fake-genblaze`
- `GET /` → the React product UI

The Firebase Hosting mirror https://upgradegr-cinemory.web.app serves the
identical app (rewrites per `firebase.json`, project `upgradegr-cinemory`).

**Degrade semantics (two layers, both honest):** at startup,
`build_provider()` / `build_storage()` use the real Genblaze/B2 backends only
when their credentials are present, otherwise falling back to the offline
fakes (with a WARNING) — `GET /health` always reports the effective
`provider`/`storage`. Per request, `_run_reel()` re-runs a failed live
generation on the offline provider against the **same real storage** and
labels the response `provider_degraded: true` + `degrade_reason`; the manifest
records the provider that actually generated the assets (an offline-path
failure still 500s). On that revision the per-request degrade fired
**only** because the GMI account balance was then zero — real B2 writes from
the live box were already proven (full object set under `mitigation-smoke-1/`
+ growing `index.jsonl`; bucket then 31 objects incl. `live-degrade-proof/`
and `chain-inputs/`). *The balance blocker closed 2026-07-22 — see below.*

### 2026-07-21 deploy history

| Revision | Code | Env | Outcome |
|---|---|---|---|
| `cinemory-00007` | pre-fix | full live | exposed the live 500 (photo inputs never reached Genblaze → GMI `400 image`) |
| `cinemory-00008` | pre-fix | live, no GMI | mitigation — 200s via degrade |
| `cinemory-00009-cjv` | **`7b6223f`** (fix) | **full live** | **current** — health above; degrade only from zero GMI balance |

B2 key history: the earlier key had zero capabilities (`AccessDenied` on
PutObject/ListObjectsV2); the owner-issued key was verified Put + List on
2026-07-21 and is live in the deploy env.

## ✅ 2026-07-22 — funded live run: REAL generation proven (+ P0 fixes to pick up)

The GMI account was funded (spend ≈$2.6) and the full live chain ran for real:
**8 completed Kling I2V renders** (~242s avg), one live seedance FLF2V bridge,
a real **h264 720p 30.6s reel** (byte-exact sha256 `db6a3281…`) on B2 — bucket
now **133 objects**, `index.jsonl` **174 rows**, sink chain verified. The live
box itself ran a real upload-path generation (265s render); that request
**504'd at Cloud Run's 300s default while completing server-side**, which is
fixed by `--timeout 600` in `deploy/deploy-cloudrun.sh` (PR `fix/live-run-p0s`,
together with the Kling-compatible 1024×576 synthetic default and the presign
region/SigV4 fix). A bucket CORS rule `cinemoryPlayback` (GET/HEAD, the two app
origins only) was added for browser playback; the bucket stays private.

**Next redeploy:** re-run `bash deploy/deploy-cloudrun.sh` with the live env
once the P0-fix PR is merged so the box picks up the synth-size, presign and
timeout fixes; then re-check `/health` and one presigned playback.

### cinemory.ai domain mapping — NOT yet mapped

`cinemory.ai` currently returns HTTP 000 (domain never mapped). Until DNS is set
up (apex → A + AAAA records — see `CLOUDRUN.md`), the judge-accessible URL is the
run.app link above.
