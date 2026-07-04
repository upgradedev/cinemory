# Cinemory — single deployable container (Cloud Run / Container Apps / Fly / etc.)
#
# One container serves BOTH the FastAPI backend AND the web client, on one port
# (Cloud Run = single container / single port). Stage 1 compiles the vanilla-TS
# web client (tsc -> dist); stage 2 is the Python runtime, and FastAPI serves the
# compiled client as static files (see cinemory.api: it mounts CINEMORY_WEB_DIR).

# ── Stage 1: build the web client (vanilla TS SPA, compiled with tsc) ────────
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/tsconfig.json ./
# No lockfile is committed (web/package-lock.json is gitignored), so install
# from package.json — the web client has a single dev dep (typescript).
RUN npm install --no-audit --no-fund
COPY web/src ./src
COPY web/index.html ./index.html
RUN npm run build          # tsc -> /web/dist

# ── Stage 2: Python runtime (FastAPI + ffmpeg for the live cinematic stitch) ─
FROM python:3.11-slim

# ffmpeg enables the real cinematic stitch path (CINEMORY_STITCH=ffmpeg).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir . "uvicorn>=0.29"

# Add the live extra at build time if deploying against real Genblaze + B2:
#   RUN pip install --no-cache-dir ".[live]"

# Static web client (index.html references ./dist/... so keep them side by side).
COPY --from=web /web/index.html ./web/index.html
COPY --from=web /web/dist ./web/dist

ENV CINEMORY_MODE=offline \
    CINEMORY_WEB_DIR=/app/web \
    PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (set by Cloud Run) is honoured; defaults to 8000 locally.
CMD ["sh", "-c", "uvicorn cinemory.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
