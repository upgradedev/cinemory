# Cinemory API — deployable container (Cloud Run / Container Apps / Fly / etc.)
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

ENV CINEMORY_MODE=offline \
    PORT=8000
EXPOSE 8000

CMD ["uvicorn", "cinemory.api:app", "--host", "0.0.0.0", "--port", "8000"]
