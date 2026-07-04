# Cinemory on Google Cloud Run

One container, one port. FastAPI serves both the JSON API **and** the compiled
web client (a vanilla-TypeScript SPA built with `tsc`, mounted as static files).
Cloud Run scales it to **zero** when idle.

| Setting | Value |
|---|---|
| GCP project | `upgradegr-cinemory` |
| Region | `europe-west1` |
| Service | `cinemory` |
| Artifact Registry repo | `cinemory` (docker) |
| Port | `8000` |
| Auth | public (`--allow-unauthenticated`) |

## Prerequisites (one-time)

```bash
gcloud auth login                       # tf@upgrade.net.gr
gcloud config set project upgradegr-cinemory
# billing must be linked (acct 01A97A-55FE41-BC2FC8) — verify:
gcloud beta billing projects describe upgradegr-cinemory
```

The deploy script enables the required APIs itself
(`run`, `cloudbuild`, `artifactregistry`) and creates the Artifact Registry repo
if missing.

## Deploy — OFFLINE (default, zero credentials)

Runs the full pipeline with fakes; no B2 / Genblaze creds needed. Good for a
working public URL and to validate the hosting pipeline.

```bash
bash deploy/deploy-cloudrun.sh
```

The script prints the service URL at the end. Verify it serves:

```bash
URL="$(gcloud run services describe cinemory --region europe-west1 \
        --format 'value(status.url)')"

curl -s "$URL/health"          # {"status":"ok","mode":"offline",...}
curl -s "$URL/occasions"       # occasion presets
curl -s -X POST "$URL/reels" -H 'content-type: application/json' \
     -d '{"name":"demo-reel","chapters":3,"per_chapter":2,"occasion":"anniversary"}'
curl -s -o /dev/null -w '%{http_code}\n' "$URL/"            # 200 (web client)
curl -s -o /dev/null -w '%{http_code}\n' "$URL/dist/main.js" # 200 (SPA bundle)
```

## Deploy — LIVE cutover (gated — see below)

The live path renders real reels with Genblaze/GMI Cloud and stores them on
Backblaze B2. It is a **one-command redeploy** with creds attached:

```bash
CINEMORY_MODE=live \
CINEMORY_STITCH=ffmpeg \
B2_APPLICATION_KEY_ID='<b2 key id>' \
B2_APPLICATION_KEY='<b2 app key>' \
B2_BUCKET_NAME='<b2 bucket>' \
B2_S3_ENDPOINT='https://s3.<region>.backblazeb2.com' \
GMI_API_KEY='<gmi cloud key>' \
  bash deploy/deploy-cloudrun.sh
```

`ffmpeg` is already installed in the image, so `CINEMORY_STITCH=ffmpeg` works.

> The script **rebuilds the image from local source**. After Gate A merges, run
> `git checkout main && git pull` **before** the cutover, or the rebuilt image
> still lacks the Option B code and the canonical B2 names silently mis-resolve.

### ⚠️ Two gates before the live command works

1. **Gate A — Option B config-fallback PR must be merged.** This live command
   uses the **canonical** B2 var names
   (`B2_APPLICATION_KEY_ID` / `B2_APPLICATION_KEY` / `B2_BUCKET_NAME` /
   `B2_S3_ENDPOINT`). The image built from the **current `main`** still reads the
   **legacy** names (`B2_KEY_ID` / `B2_APP_KEY` / `B2_BUCKET_NAME` /
   `B2_ENDPOINT_URL` / `B2_REGION`). Until the Option B PR merges, either merge it
   first (recommended) **or** pass the legacy names instead. Running the canonical
   command against today's image would silently fall back / mis-read creds.
2. **Gate B — `GMI_API_KEY` not yet issued.** GMI Cloud gives ~270 free credits;
   create the key, then supply it above.

Once both gates clear, the single command above is the entire cutover.

## Domain mapping — cinemory.ai

`cinemory.ai` is an **apex** domain, so it maps via **A + AAAA** records
(a CNAME is only valid for a subdomain like `www`).

**User prerequisite:** verify domain ownership first — Cloud Run domain mapping
refuses an unverified domain.

```bash
# 1. Verify ownership (opens Search Console; add the TXT record it shows to DNS)
gcloud domains verify cinemory.ai

# 2. Create the mapping
gcloud beta run domain-mappings create \
  --service cinemory --domain cinemory.ai --region europe-west1

# 3. Read the exact DNS records Google wants (do NOT guess the IPs)
gcloud beta run domain-mappings describe \
  --domain cinemory.ai --region europe-west1 \
  --format='value(status.resourceRecords)'
```

> `run domain-mappings` is not offered in every region. `europe-west1` is
> expected to support it; if `create` returns a region error, either map from a
> supported region or front the service with a global external HTTPS load
> balancer + a serverless NEG (the portable fallback) and point `cinemory.ai` at
> the LB's IP instead.

Step 3 prints four **A** records (IPv4) and four **AAAA** records (IPv6). Add
them at the registrar for the apex (`@`) host. For `www.cinemory.ai`, map that
domain too and add the single **CNAME → ghs.googlehosted.com** it returns.
TLS is provisioned automatically once DNS resolves (can take up to ~1 hour).

## Cost profile

Scales to zero — **no idle cost**. You pay only per request-second while a
container is warm:

| Item | Estimate |
|---|---|
| Cloud Run (idle) | $0 (min-instances=0) |
| Cloud Run (active) | ~$0.00002400/vCPU-s + ~$0.00000250/GiB-s; demo traffic ≈ cents/day |
| Artifact Registry | ~$0.10/GB-month (one small image) |
| Cloud Build | 120 free build-min/day; this image builds well within it |
| Domain mapping / managed TLS | free |

Practical: a low-traffic demo on cinemory.ai costs **~$0–2/month**.
