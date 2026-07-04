# Cinemory — deploy record

## 2026-07-04 — first Cloud Run deploy (OFFLINE, validated)

| | |
|---|---|
| Project | `upgradegr-cinemory` (billing `01A97A-55FE41-BC2FC8`) |
| Region | `europe-west1` |
| Service | `cinemory` |
| Revision | `cinemory-00001-7sm` |
| Image | `europe-west1-docker.pkg.dev/upgradegr-cinemory/cinemory/cinemory:20260704-175240` |
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

### Live cutover (still gated — not executed)

Gate A: merge the Option B config-fallback PR (today's image reads legacy B2 var
names). Gate B: obtain `GMI_API_KEY`. Then one command (see `CLOUDRUN.md`):

```bash
CINEMORY_MODE=live CINEMORY_STITCH=ffmpeg \
B2_APPLICATION_KEY_ID=... B2_APPLICATION_KEY=... \
B2_BUCKET_NAME=... B2_S3_ENDPOINT=... GMI_API_KEY=... \
  bash deploy/deploy-cloudrun.sh
```

### cinemory.ai domain mapping — see `CLOUDRUN.md` (apex → A + AAAA records).
