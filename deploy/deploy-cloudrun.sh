#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Turnkey Cloud Run deploy for Cinemory.
#
#   • builds the image with Cloud Build (no local Docker — cloud-first)
#   • pushes to Artifact Registry
#   • deploys a public Cloud Run service on port 8000
#
# OFFLINE (default) needs ZERO credentials — the app runs the full pipeline with
# fakes. Flip to the LIVE path by passing the creds below (see deploy/CLOUDRUN.md).
#
# Usage:
#   bash deploy/deploy-cloudrun.sh                 # offline deploy (default)
#   CINEMORY_MODE=live \
#   B2_APPLICATION_KEY_ID=... B2_APPLICATION_KEY=... \
#   B2_BUCKET_NAME=... B2_S3_ENDPOINT=... GMI_API_KEY=... \
#     bash deploy/deploy-cloudrun.sh              # live deploy
#
# Every knob is an env var with a sane default:
#   PROJECT_ID REGION SERVICE AR_REPO IMAGE_TAG CINEMORY_MODE CINEMORY_STITCH
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-upgradegr-cinemory}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-cinemory}"
AR_REPO="${AR_REPO:-cinemory}"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/cinemory:${IMAGE_TAG}"

CINEMORY_MODE="${CINEMORY_MODE:-offline}"
CINEMORY_STITCH="${CINEMORY_STITCH:-fake}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▶ project=${PROJECT_ID}  region=${REGION}  service=${SERVICE}  mode=${CINEMORY_MODE}"
echo "▶ image=${IMAGE}"

# ── 1. Target project + required APIs ────────────────────────────────────────
gcloud config set project "${PROJECT_ID}" >/dev/null
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  --project "${PROJECT_ID}"

# ── 2. Artifact Registry repo (idempotent) ───────────────────────────────────
if ! gcloud artifacts repositories describe "${AR_REPO}" \
      --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "▶ creating Artifact Registry repo '${AR_REPO}' in ${REGION}"
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format docker --location "${REGION}" \
    --description "Cinemory container images" --project "${PROJECT_ID}"
fi

# ── 3. Build the image with Cloud Build ──────────────────────────────────────
gcloud builds submit "${REPO_ROOT}" \
  --config "${REPO_ROOT}/deploy/cloudbuild.yaml" \
  --substitutions "_IMAGE=${IMAGE}" \
  --project "${PROJECT_ID}"

# ── 4. Assemble runtime env vars for the chosen mode ─────────────────────────
ENV_VARS="CINEMORY_MODE=${CINEMORY_MODE},CINEMORY_STITCH=${CINEMORY_STITCH}"

if [ "${CINEMORY_MODE}" = "live" ]; then
  : "${B2_APPLICATION_KEY_ID:?live mode needs B2_APPLICATION_KEY_ID}"
  : "${B2_APPLICATION_KEY:?live mode needs B2_APPLICATION_KEY}"
  : "${B2_BUCKET_NAME:?live mode needs B2_BUCKET_NAME}"
  : "${B2_S3_ENDPOINT:?live mode needs B2_S3_ENDPOINT}"
  : "${GMI_API_KEY:?live mode needs GMI_API_KEY}"
  ENV_VARS="${ENV_VARS}"
  ENV_VARS="${ENV_VARS},B2_APPLICATION_KEY_ID=${B2_APPLICATION_KEY_ID}"
  ENV_VARS="${ENV_VARS},B2_APPLICATION_KEY=${B2_APPLICATION_KEY}"
  ENV_VARS="${ENV_VARS},B2_BUCKET_NAME=${B2_BUCKET_NAME}"
  ENV_VARS="${ENV_VARS},B2_S3_ENDPOINT=${B2_S3_ENDPOINT}"
  ENV_VARS="${ENV_VARS},GMI_API_KEY=${GMI_API_KEY}"
  # Optional provider override (defaults to gmicloud in the app).
  [ -n "${GENBLAZE_PROVIDER:-}" ] && ENV_VARS="${ENV_VARS},GENBLAZE_PROVIDER=${GENBLAZE_PROVIDER}"
fi

# ── 5. Deploy to Cloud Run (public, port 8000, scales to zero) ───────────────
# --timeout 600: a real single-clip live generation measures ~330-350s end-to-end
# (Kling render ~242s avg + hosting/stitch/provenance). Cloud Run's 300s default
# 504'd those requests at the edge while the reel completed server-side
# (proven live 2026-07-22), so the request deadline must sit above the real path.
gcloud run deploy "${SERVICE}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8000 \
  --timeout 600 \
  --cpu 1 --memory 512Mi \
  --min-instances 0 --max-instances 4 \
  --set-env-vars "${ENV_VARS}" \
  --project "${PROJECT_ID}"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" \
        --project "${PROJECT_ID}" --format 'value(status.url)')"
echo "✓ deployed: ${URL}"
echo "  health : ${URL}/health"
echo "  webapp : ${URL}/"
