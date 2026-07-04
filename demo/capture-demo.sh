#!/usr/bin/env bash
# Cinemory demo capture — drives the exact flow shown in the video.
#
#   OFFLINE (default, no creds):   bash demo/capture-demo.sh
#   LIVE (real Genblaze + B2):     CINEMORY_MODE=live bash demo/capture-demo.sh
#
# Offline runs the real pipeline + real SHA-256 provenance with fakes at the
# network boundary only. Live requires a filled .env (B2_* + GMI_API_KEY) and
# hits real Genblaze + Backblaze B2.
set -euo pipefail

OUT="${OUT:-demo/out}"
NAME="${NAME:-cinemory-demo}"
OCCASION="${OCCASION:-anniversary}"
MODE="${CINEMORY_MODE:-offline}"

echo "=============================================================="
echo " Cinemory demo — mode=${MODE}  occasion=${OCCASION}"
echo "=============================================================="

if [ "$MODE" = "live" ]; then
  [ -f .env ] && set -a && . ./.env && set +a || true
  export CINEMORY_MODE=live
  export CINEMORY_STITCH="${CINEMORY_STITCH:-ffmpeg}"
  : "${B2_BUCKET_NAME:?set B2_* in .env for live mode}"
  : "${GMI_API_KEY:?set GMI_API_KEY in .env for live mode}"
fi

echo
echo "[1/4] Install (editable) ..."
pip install -q -e . >/dev/null

echo "[2/4] Materialise PII-safe synthetic input photos ..."
python scripts/generate_demo.py --out sample-data/generated --count 6

echo "[3/4] Generate the reel end-to-end (photos -> clips -> bridges -> reel -> B2 -> provenance) ..."
rm -rf "$OUT"
python -m cinemory.cli \
  --name "$NAME" --chapters 3 --per-chapter 2 --bridges \
  --occasion "$OCCASION" --out "$OUT"

echo
echo "[4/4] Re-verify provenance offline (independent of the run) ..."
python - "$OUT/manifest.json" "$OUT/reel.provenance.mp4" <<'PY'
import sys, json, hashlib, pathlib
manifest_path, embedded_reel = sys.argv[1], sys.argv[2]
manifest = json.loads(pathlib.Path(manifest_path).read_text())
print("  manifest steps:", len(manifest.get("steps", [])))
print("  reel sha256   :", manifest.get("reel_asset", {}).get("sha256", "n/a"))
print("  manifest hash :", manifest.get("manifest_hash", "n/a"))
data = pathlib.Path(embedded_reel).read_bytes()
print("  embedded reel :", len(data), "bytes on disk")
print("  OK — manifest re-loaded and hashes present.")
PY

echo
echo "Artifacts in $OUT/ :"
ls -la "$OUT"
echo
echo "Done. For the video, screen-record steps [3] and [4] and (live) the B2 bucket browser."
