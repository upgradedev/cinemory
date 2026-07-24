# Cinemory on Google Cloud Run

One container, one port. FastAPI serves both the JSON API **and** the compiled
web client (the `frontend/` React SPA, built with Vite and mounted as static
files — the Dockerfile builds it into the image). Cloud Run scales it to **zero**
when idle.

| Setting | Value |
|---|---|
| GCP project | `upgradegr-cinemory` |
| Region | `europe-west1` |
| Service | `cinemory` |
| Artifact Registry repo | `cinemory` (docker) |
| Port | `8000` |
| Auth | public (`--allow-unauthenticated`) |
| Request timeout | `600s` (`--timeout 600` — see note below) |

> **Why 600s:** a real single-clip live generation measures **~330–350s**
> end-to-end (Kling render ≈242s avg + input hosting, stitch, provenance,
> B2 writes). Cloud Run's 300s default returned **504** to the client while
> the reel completed server-side (observed live 2026-07-22). The deploy
> script pins `--timeout 600` so synchronous `POST /reels*` requests outlive
> the real generation path.

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
curl -s -o /dev/null -w '%{http_code}\n' "$URL/"            # 200 (React SPA index)
curl -s "$URL/" | grep -qo '/assets/[^"]*\.js' && echo "SPA bundle referenced (Vite /assets/*)"
```

## Deploy — LIVE cutover (secrets via Secret Manager)

The live path renders real reels with Genblaze/GMI Cloud and stores them on
Backblaze B2. Secret values are **never** passed on the command line or written
to the Cloud Run service spec — they live in **Google Secret Manager** and are
staged once (and on every rotation) with `deploy/stage-secrets.sh`; the deploy
then references them by name. That way `gcloud run services describe` — and
anyone with only `run.services.get` IAM on the project — never sees a raw key.

**Step 1 — stage the secrets** (this is the only step that handles raw values;
run it on first setup and on each key rotation):

```bash
B2_APPLICATION_KEY_ID='<b2 key id>' \
B2_APPLICATION_KEY='<b2 app key>' \
GMI_API_KEY='<gmi cloud key>' \
  bash deploy/stage-secrets.sh
```

It creates/updates three Secret Manager secrets
(`cinemory-b2-application-key-id`, `cinemory-b2-application-key`,
`cinemory-gmi-api-key`). Prefer not to put keys in a shell? Create the same
three secrets in the Cloud Console (Secret Manager → Create secret) instead.

**Step 2 — deploy** (no secret values here — only the non-secret live config):

```bash
CINEMORY_MODE=live \
CINEMORY_STITCH=ffmpeg \
B2_BUCKET_NAME=cinemory \
B2_S3_ENDPOINT='https://s3.<region>.backblazeb2.com' \
  bash deploy/deploy-cloudrun.sh
```

The deploy script grants the Cloud Run runtime service account
`roles/secretmanager.secretAccessor` on each secret, then wires them with
`--set-secrets` (env var ← `<secret>:latest`). It fails fast with a pointer back
to step 1 if a secret is missing. `ffmpeg` is already in the image, so
`CINEMORY_STITCH=ffmpeg` works.

> The script **rebuilds the image from local source**. Run
> `git checkout main && git pull` **before** the cutover so the rebuilt image
> carries the latest code.

### Rotating keys

Issue new keys in the GMI Cloud / Backblaze dashboards, re-run **step 1** with
the new values (adds a new secret version), re-run **step 2**, verify `/health`,
then revoke the old keys. Cloud Run reads `:latest`, so the redeploy picks up
the new version with no code change — and the old plaintext-env-var exposure is
gone for good.

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
