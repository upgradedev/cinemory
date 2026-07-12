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

## ⚠️ Current live state — `live` mode; deployed revision predates the degrade fix

The service was later redeployed with `CINEMORY_MODE=live` **without** attaching
B2/GMI credentials. The *currently-deployed* revision runs the pre-fix image:

- `GET /health` → `{"status":"ok","service":"cinemory-api","mode":"live"}` (serves)
- `POST /reels` → **HTTP 500** on that old revision — no Genblaze/B2 credentials.

**The code now guarantees this can't recur.** `build_provider()` / `build_storage()`
use the real Genblaze/B2 backends only when their credentials are present, and
otherwise degrade transparently to the offline fakes (with a WARNING). So in
`live` mode with no creds, `POST /reels` returns 200 with a real deterministic
reel + sealed manifest, and `GET /health` reports the effective
`provider`/`storage`.

**Owner-only step — redeploy the latest image.** That alone clears the 500 (no
creds or mode change needed). Attach `GMI_API_KEY` + the B2 vars only to get
*real* live generation instead of the offline-degraded path.

Gate B (`GMI_API_KEY` not yet issued) still applies to the real-generation path.
Live command (see `CLOUDRUN.md`):

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
