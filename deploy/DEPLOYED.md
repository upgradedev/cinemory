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

## ⚠️ Current live state — cut over to `live`, but BROKEN (no creds)

The service was later redeployed with `CINEMORY_MODE=live` **without** attaching
B2/GMI credentials. As a result the live revision is in a half-broken state:

- `GET /health` → `{"status":"ok","service":"cinemory-api","mode":"live"}` (serves)
- `POST /reels` → **HTTP 500** — the core generate action fails because no
  Genblaze/B2 credentials are present in the live revision.

This contradicts a working demo. **Owner-only fix (pick one):**
- **Attach creds + redeploy** — supply `GMI_API_KEY` + the B2 vars via the live
  command below, or
- **Revert to offline** — redeploy with `CINEMORY_MODE=offline` (`CINEMORY_STITCH=fake`)
  so `POST /reels` returns a full offline reel again.

Gate B (`GMI_API_KEY` not yet issued) still applies to the creds path. Live command
(see `CLOUDRUN.md`):

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
