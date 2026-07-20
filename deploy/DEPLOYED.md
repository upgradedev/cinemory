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

## ✅ Current live state — verified 2026-07-21 (honest offline-degrade mode)

The deployed revision runs the degrade-to-offline image and is healthy.
Verified against the live service on 2026-07-21:

- `GET /health` → 200
  `{"status":"ok","service":"cinemory-api","mode":"offline","provider":"fake-genblaze","storage":"FakeStorage"}`
- `GET /occasions` → 200 (6 occasion themes)
- `POST /reels` → **200** — sealed reel + provenance manifest, zero credentials
- `GET /` → the React product UI

The Firebase Hosting mirror https://upgradegr-cinemory.web.app serves the
identical app (rewrites per `firebase.json`, project `upgradegr-cinemory`).

`build_provider()` / `build_storage()` use the real Genblaze/B2 backends only
when their credentials are present, and otherwise degrade transparently to the
offline fakes (with a WARNING) — so the core action never 500s and `GET /health`
always reports the effective `provider`/`storage`.

### 2026-07-21 — live-mode redeploy pending a write-entitled B2 key

The configured B2 application key authenticates but carries **zero
capabilities**: PutObject and ListObjectsV2 both return
`AccessDenied: not entitled` (probed 2026-07-21). The endpoint
(`s3.eu-central-003.backblazeb2.com`) and the bucket (`cinemory`) are correct —
the key itself lacks entitlements. A new write-entitled key is pending from the
owner; the real live run and the `CINEMORY_MODE=live` redeploy are gated on it
(the real-generation path also needs `GMI_API_KEY`).

Live command once the key exists (see `CLOUDRUN.md`):

```bash
CINEMORY_MODE=live CINEMORY_STITCH=ffmpeg \
B2_APPLICATION_KEY_ID=... B2_APPLICATION_KEY=... \
B2_BUCKET_NAME=... B2_S3_ENDPOINT=... GMI_API_KEY=... \
  bash deploy/deploy-cloudrun.sh
```

### cinemory.ai domain mapping — NOT yet mapped

`cinemory.ai` currently returns HTTP 000 (domain never mapped). Until DNS is set
up (apex → A + AAAA records — see `CLOUDRUN.md`), the judge-accessible URL is the
run.app link above.
