# Cinemory — ~3-minute demo video script

Target: ~3:00. Screen-record; talk over it. Judges score Real-World Utility,
Production Readiness, B2 use, Genblaze use — hit each explicitly.

> Record the **live** run if credentials are ready (best evidence for B2 +
> Genblaze). If not, the **offline** run shows the identical pipeline and real
> provenance — say so on camera; do not fake a live result.

---

## 0:00–0:20 — Hook + what it is
- On camera / title card: "Cinemory turns your photos into a scored cinematic
  film — generated with Genblaze, stored on Backblaze B2, and sealed with
  verifiable SHA-256 provenance on every frame it produces."
- One line of origin: "It started as an anniversary gift — photos into a short
  film. The personal content stays private; this demo uses synthetic photos
  only."

## 0:20–0:45 — The problem (Real-World Utility)
- "AI media is easy to make and hard to trust. For a comms team turning an event's
  photos into a branded highlight reel, three questions matter: what made this,
  from what inputs, and can I prove it wasn't tampered with. Cinemory answers all
  three."

## 0:45–1:40 — Run it (the core demo)
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
- Point at the printed output: `stored objects: 17`, `verify manifest: True`,
  `verify asset: True`, `verify embedded: True`.

## 1:40–2:10 — Provenance is real (differentiator)
- Show `manifest.json`: provider, model, prompt, params, timestamps, every asset
  hash.
- "This manifest is embedded *into* the reel container and re-verifiable offline —
  step [4] just re-loaded it and confirmed the hashes with no network."
- (Live) Flip to the **B2 bucket browser** — show the content-addressed keys and
  the `manifest.json` sitting next to the assets.

## 2:10–2:40 — Production readiness
- "Ports-and-adapters: live↔offline is a one-line swap. 67 tests pass offline
  with zero credentials — including a contract test that runs the adapter against
  the **real published Genblaze SDK**, so API drift fails CI."
- Flash the green GitHub Actions run (gitleaks · CodeQL · pip-audit · npm audit ·
  ruff) and the Dockerfile.

## 2:40–3:00 — Close
- "Genblaze for generation and per-asset provenance; Backblaze B2 for durable,
  content-addressed storage of every artifact; provenance you can verify. That's
  Cinemory — memories, made into film, that you can trust."
- End card: repo URL + cinemory.ai.

---

### Shot list / B-roll
- The printed CLI summary block (reel/manifest/verify lines).
- `out/reel.provenance.mp4` playing a few seconds.
- `manifest.json` scrolled once.
- (Live) B2 bucket browser with content-addressed prefixes.
- GitHub Actions all-green checks.
