# Cinemory — ~3.5-minute demo video script

Target: ~3:30. Screen-record; talk over it. Judges score Real-World Utility,
Production Readiness, B2 use, Genblaze use — hit each explicitly.

> Record the **live** run if credentials are ready (best evidence for B2 +
> Genblaze). If not, the **offline** run shows the identical pipeline and real
> provenance — say so on camera; do not fake a live result. The app never 500s
> either way (see the degrade beat), so the demo is safe to record live.

---

## 0:00–0:20 — Hook + what it is
- On camera / title card: "Cinemory turns your photos into a scored cinematic
  film — generated with Genblaze, stored on Backblaze B2, and sealed with
  verifiable SHA-256 provenance on every frame it produces."
- One line of origin: "It started as an anniversary gift — photos into a short
  film. The personal content stays private; this demo uses synthetic photos
  only."

## 0:20–0:40 — The problem (Real-World Utility)
- "AI media is easy to make and hard to trust. For a comms team turning an event's
  photos into a branded highlight reel, three questions matter: what made this,
  from what inputs, and can I prove it wasn't tampered with. Cinemory answers all
  three."

## 0:40–1:25 — The product: the React wizard, real photos (headline)
Screen-record the live web client (https://upgradegr-cinemory.web.app, or
`npm --prefix frontend run dev`). Drive the full four-step wizard end-to-end:
- **Photos** — drag-and-drop a handful of real photos onto the storyboard;
  reorder a couple of thumbnails. "These are *your* actual pixels — the bytes,
  not just a count."
- **Occasion** — pick an occasion card (e.g. Anniversary). "The occasion sets
  music mood, pacing and aspect ratio, and it's sealed into the manifest."
- **Generate** — hit generate. "The real photo bytes stream to
  `POST /reels/upload-multipart`; the pipeline animates each photo, bridges the
  chapters, stitches, stores to B2, and seals provenance — the progress list is
  the honest server pipeline."
- **Result + Provenance panel** — the reel plays; open the **Provenance** panel.
  "Every step's Genblaze hash, the SHA-256 manifest seal and the storage badge —
  fetched from `GET /reels/{name}`, which reads the same queryable run index the
  backend keeps in B2." Point at the per-step hashes and the manifest seal.

## 1:25–2:05 — The pipeline in the raw (CLI)
- Terminal: `bash demo/capture-demo.sh`  (or `CINEMORY_MODE=live bash demo/capture-demo.sh`).
- Narrate as it runs:
  - "Synthetic photos are generated — no real personal data."
  - "Each photo becomes a short clip through a **Genblaze pipeline step** — an
    image-to-video model (Kling via GMI Cloud). Chapters are bridged with
    first-last-frame transitions."
  - "Genblaze content-addresses each generated asset, persists it to **Backblaze
    B2**, and seals a SHA-256 manifest for it."
  - "Cinemory stitches the reel with a real ffmpeg cinematic grade and writes the
    reel + reel-level manifest to B2."
- Point at the printed output: `stored objects:  17`, `verify manifest: True`,
  `verify asset:    True`, `verify embedded: True`.

## 2:05–2:35 — Provenance is real, and tamper-evident (differentiator)
- Show `manifest.json`: provider, model, prompt, params, timestamps, every asset
  hash.
- "This manifest is embedded *into* the reel container and re-verifiable offline —
  step [4] just re-loaded it and confirmed the hashes with no network."
- **Tamper beat:** run `pytest tests/unit/test_provenance.py -q` on camera and
  point at `test_manifest_tamper_is_detected` — "flip a single byte in a sealed
  asset and verification fails. Trust isn't a claim; it's a test."
- (Live) Flip to the **B2 bucket browser** — show the content-addressed keys and
  the `manifest.json` sitting next to the assets.

## 2:35–3:05 — Production readiness (never-500 + SDK contract)
- "The core action never 500s. In `live` mode the API uses the real Genblaze/B2
  backends only when their credentials are present, and otherwise degrades
  transparently to the offline path." Show `GET /health` reporting the effective
  `provider`/`storage`, then `POST /reels` returning **200** with a sealed
  manifest even with no creds.
- "Ports-and-adapters: live↔offline is a one-line swap. The whole suite runs
  green offline with zero credentials — 154 tests (one ffmpeg-conditional skip in
  CI) — including a contract test that runs the adapter against the **real
  published Genblaze SDK**, so API drift fails CI." Run
  `pytest tests/integration/test_genblaze_contract.py -q` on camera.
- Flash the green GitHub Actions run (gitleaks · CodeQL · pip-audit · npm audit ·
  ruff).

## 3:05–3:30 — Close
- "Genblaze for generation and per-asset provenance; Backblaze B2 for durable,
  content-addressed storage of every artifact plus a queryable run index;
  provenance you can verify and that fails loudly when tampered. That's
  Cinemory — memories, made into film, that you can trust."
- End card: repo URL (github.com/upgradedev/cinemory) + the live app
  (upgradegr-cinemory.web.app / the run.app service URL).

---

### Shot list / B-roll
- The React wizard: drag-drop photos → occasion → generate → Result + Provenance
  panel (per-step hashes, manifest seal, storage badge).
- The printed CLI summary block (reel/manifest/verify lines, `stored objects: 17`).
- `out/reel.provenance.mp4` playing a few seconds.
- `manifest.json` scrolled once.
- `pytest tests/unit/test_provenance.py` — the tamper test.
- `pytest tests/integration/test_genblaze_contract.py` — the SDK contract test.
- `GET /health` + a 200 `POST /reels` proving the never-500 degrade.
- (Live) B2 bucket browser with content-addressed prefixes.
- GitHub Actions all-green checks.
