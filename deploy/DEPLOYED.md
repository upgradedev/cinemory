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
failure still 500s). On the current revision the per-request degrade fires
**only** because the GMI account balance is zero — real B2 writes from the
live box are proven (full object set under `mitigation-smoke-1/` + growing
`index.jsonl`; bucket total 31 objects incl. `live-degrade-proof/` and
`chain-inputs/`).

### 2026-07-21 deploy history

| Revision | Code | Env | Outcome |
|---|---|---|---|
| `cinemory-00007` | pre-fix | full live | exposed the live 500 (photo inputs never reached Genblaze → GMI `400 image`) |
| `cinemory-00008` | pre-fix | live, no GMI | mitigation — 200s via degrade |
| `cinemory-00009-cjv` | **`7b6223f`** (fix) | **full live** | **current** — health above; degrade only from zero GMI balance |

B2 key history: the earlier key had zero capabilities (`AccessDenied` on
PutObject/ListObjectsV2); the owner-issued key was verified Put + List on
2026-07-21 and is live in the deploy env.

**No redeploy needed for real generation:** the deployed revision already runs
the fixed code with the full live env. The only remaining blocker is the GMI
account credits top-up (owner-held). Once topped up,
`CINEMORY_MODE=live bash demo/capture-demo.sh` is expected to pass unchanged
and the live box starts producing real generations as-is.

### cinemory.ai domain mapping — NOT yet mapped

`cinemory.ai` currently returns HTTP 000 (domain never mapped). Until DNS is set
up (apex → A + AAAA records — see `CLOUDRUN.md`), the judge-accessible URL is the
run.app link above.
