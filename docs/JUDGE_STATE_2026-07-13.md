# Judge State — Cinemory — 2026-07-13

> Single source of truth for any agent/AI opening this repo: where this build stands against the
> Backblaze Generative Media Challenge rubric, what was harmonized in the 2026-07-12/13 session, and
> the ranked path to **exceed the target bar (> 90 / 100)**. Derived from the workspace judgment
> review (`JUDGMENT_REVIEW_2026-07-12.md`, CINEMORY section), re-verified against this repo on
> 2026-07-13.
>
> The demo video (`demo/cinemory-demo.mp4`) and the blog/write-up are treated as **done /
> ready-to-submit** and are deliberately excluded from the path below.

## Challenge + target

| | |
|---|---|
| Challenge | Backblaze Generative Media Challenge |
| Deadline | **2026-08-03** (5:00pm EDT) |
| Rubric | 4 criteria (scored **/100**): Real-World Utility · Production Readiness · B2 Storage & Orchestration · Use of Genblaze |
| Target bar to exceed | **> 90 / 100** |
| Current judged score | **~82 / 100** (was ~72–78 pre-harmony; lifted by merged PRs #7–#10) |

> Note on scores: the repo's own `demo/STATE.md` scorecard self-assesses ~92/100. This doc carries the
> more conservative external judgment-review figure (~82/100), which discounts criteria 3 and 4 because
> the real-B2-write and real-Genblaze-generation paths are code-complete + verified but **not yet
> exercised live** (the deploy currently runs the offline-degrade path — see the per-criterion notes).

## Current judge score — per criterion

Each expressed on a 0–10 scale; aggregate lands ~82/100.

| Criterion | Score | Notes |
|---|---|---|
| Real-World Utility | ~8 | Consumer memory-gift + B2B event/award-ceremony wedge; six occasion themes; real-photo ingest now wired end-to-end (mobile/web send actual pixels). Unchanged and strong. |
| Production Readiness | ~8 | **Was the weakness — both live-surface defects fixed this session.** (1) Firebase host served a leaked private anniversary film → rebuilt + `firebase deploy` so `upgradegr-cinemory.web.app` now serves the React product UI. (2) Cloud Run `POST /reels` returned 500 with no creds → `build_provider()`/`build_storage()` degrade transparently to offline fakes, so `POST /reels` **never 500s** and `/health` reports the effective backends. 154 backend tests (153 pass + 1 ffmpeg-conditional skip in CI) + 21 frontend; Genblaze SDK contract test; ruff clean. |
| B2 Storage & Orchestration | ~8 | Content-addressed keys for every input/clip/reel/manifest + a durable, queryable `index.jsonl` run index (per-put write + query-time reload) so `GET /reels/{name}` and the ProvenancePanel resolve. **Proven in FakeStorage/offline + unit-tested** (multi-instance resolution, non-empty prefix, 5 tests); the real B2 object-write path is code-complete but **not yet exercised against real B2** — the deploy key is not entitled for `PutObject`, so the live box runs the offline-degrade path. |
| Use of Genblaze | ~8 | Load-bearing across gen + sink + manifest; adapter **verified against the real published Genblaze SDK** (genblaze-core/-s3 0.3.4, -gmicloud 0.3.2) and contract-tested in CI; sink→store→readback covered offline. A **real generated reel has not yet been produced live** (`GMI_API_KEY` not issued → offline-degrade), so this remains proven-in-principle rather than demonstrated-live. |

## Discrepancies fixed this session (merged PRs)

All four are merged to `main`.

- **#10** — resolve judgment-review discrepancies + demo video + live fixes. Made the `B2Storage`
  `index.jsonl` run index real (durable in-bucket catalogue, re-read at query time) so the
  ProvenancePanel works in live mode not just offline; `Footer.tsx` truthfulness fix; Dockerfile /
  `frontend/README` / `demo/STATE` reconciled to the React-serving container; committed the demo video
  (`demo/cinemory-demo.mp4`) + `demo/build-video.py`. Also records the two **CRITICAL live-surface
  fixes** (deployed, not in-diff): the **Firebase private-film leak** and the **Cloud Run `POST /reels`
  500**, both addressed.
- **#9** — frontend now streams **real photo bytes** to `POST /reels/upload-multipart` (was posting
  only count/order to the synthetic endpoint); raw pixels flow through `cinemory.ingest` →
  ObjectStorageSink → pipeline and seal genuine SHA-256 provenance.
- **#8** — **degrade-to-offline live path** (`POST /reels` never 500s with no creds; `/health` reports
  effective backends) + real-photo ingest endpoints (`POST /reels/upload` base64 JSON, `POST
  /reels/upload-multipart` multipart); invalid requests → 400 not 500.
- **#7** — reconcile status docs (`STATE.md` / `DEPLOYED.md` / `SUBMISSION.md`) with the live Cloud Run
  state (live-but-was-broken, honestly stated) + fix the dead submission URL (`cinemory.ai` HTTP 000 →
  the working `...run.app` link).

**Already resolved / verified in-repo (do not re-list as pending):** the Firebase private-film leak is
fixed (host serves the React product UI); the Cloud Run 500 is structurally impossible now
(credential-free path always returns 200 with a real deterministic reel + sealed manifest); the
Genblaze adapter is SDK-verified + contract-tested.

## Path to exceed the target (> 90) — ranked

> Demo video + blog/write-up excluded (done / ready-to-submit). Ordered by score leverage against the
> 4-criterion rubric.

1. **[USER — creds/deploy] Provision a write-entitled B2 application key + run ONE real live generation
   end-to-end.** This is the single biggest lift toward >90. A B2 key **entitled for `PutObject`** plus
   a valid `GMI_API_KEY` (GMI Cloud gives ~270 free credits), then
   `CINEMORY_MODE=live bash demo/capture-demo.sh` for one live reel, turns criterion **3 (B2 Storage —
   real objects written + a real `index.jsonl` in-bucket)** and criterion **4 (Use of Genblaze — a real
   generated reel, not the deterministic fallback)** from "offline-degrade / code-complete" into fully
   demonstrated. Without this, both criteria stay capped at ~8.
2. **[USER — creds/deploy] Redeploy Cloud Run with the write-entitled creds attached + confirm the live
   demo URL resolves.** The current revision runs offline-degrade; `bash deploy/deploy-cloudrun.sh` with
   `GMI_API_KEY` + the entitled B2 vars makes a judge hitting the run.app URL see real live generation.
   Confirm `https://cinemory-595784992266.europe-west1.run.app/health` reports
   `mode=live, provider=genblaze, storage=B2Storage` (not the offline fakes). Optionally map
   `cinemory.ai` (currently HTTP 000 / unmapped) so the judge URL is the branded domain.
3. **[CODE — buildable] Add a live-B2 smoke check to `demo/capture-demo.sh` (or a `make verify-live`
   target)** that asserts the reel + manifest objects actually landed in the bucket and the
   `index.jsonl` grew, so the live run is self-verifying evidence rather than a claim. The offline smoke
   path already exists; this extends it to the live path once creds exist.
4. **[CODE — buildable] Surface the ProvenancePanel against a real live manifest in the UI/README** —
   the panel already renders offline; once a live reel exists (item 1), capture it so *B2 Storage &
   Orchestration* is legible on sight to a fast-reading judge.

## Verified-harmonized (no action needed)

- **Two-UI ambiguity resolved:** `frontend/` is the **product** React/Vite client (built into the Cloud
  Run image and served under `/assets/*`; also on Firebase Hosting); `web/` is the **legacy/reference**
  TS SPA — still type-checked/built/audited by CI's `web` job but **no longer served**.
- **Test counts are truthful:** 154 backend collected (153 pass + 1 ffmpeg-conditional skip in CI) +
  21 frontend; ruff clean.
- **`POST /reels` is offline-safe by construction** — degrades to deterministic fakes with a WARNING
  when live is requested without ready creds; `/health` reports the effective `provider`/`storage`.
- **Six API endpoints** are consistent across README and code: `GET /health` · `GET /occasions` ·
  `POST /reels` · `POST /reels/upload` · `POST /reels/upload-multipart` · `GET /reels/{name}`.
- **Provenance is real offline** — SHA-256-sealed manifest built + verified + embedded on every run,
  independent of live credentials.
