# Cinemory — single deployable container (Cloud Run / Container Apps / Fly / etc.)
#
# One container serves BOTH the FastAPI backend AND the web client, on one port
# (Cloud Run = single container / single port). Stage 1 compiles the vanilla-TS
# web client (tsc -> dist); stage 2 is the Python runtime, and FastAPI serves the
# compiled client as static files (see cinemory.api: it mounts CINEMORY_WEB_DIR).

# ── Stage 1: build the web client (Vite React SPA) ────────
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build          # vite build -> /web/dist

# ── Stage 2: Python runtime (FastAPI + ffmpeg for the live cinematic stitch) ─
FROM python:3.11-slim

# ffmpeg enables the real cinematic stitch path (CINEMORY_STITCH=ffmpeg).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
# Install the [live] extra (boto3 + genblaze[gmicloud]) so the SAME image can run
# either mode — offline (fakes, default) or live (real Genblaze + B2) — with the
# mode chosen at runtime via CINEMORY_MODE. boto3 backs Cinemory's own reel->B2
# storage; without it, live-mode startup crashes (B2Storage import).
RUN pip install --no-cache-dir ".[live]" "uvicorn>=0.29"

# Static web client (Vite React SPA: index.html is inside dist/)
COPY --from=web /web/dist ./web

ENV CINEMORY_MODE=offline \
    CINEMORY_WEB_DIR=/app/web \
    PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (set by Cloud Run) is honoured; defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn cinemory.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
