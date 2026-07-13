# Cinemory — Web Client

A premium, cinematic single-page app for **Cinemory**: turn photos into a scored,
provenance-sealed memory reel. This is the flagship UI that Firebase Hosting
serves; the FastAPI backend on Cloud Run provides the API.

> Stack: **Vite · React 18 · TypeScript (strict) · Tailwind CSS · shadcn-style UI ·
> TanStack React Query · Zod · Zustand · framer-motion · lucide-react**. Tests: Vitest.

## The flow

A four-step cinematic wizard (landing → studio):

1. **Hero** — dark filmic identity (grain, letterbox, gold-on-black), one CTA.
2. **Photos** — drag-drop + file picker, reorderable thumbnail storyboard, remove,
   tasteful empty state. The selected photos' **actual bytes** are the input to
   the reel; the count shapes how many chapters it spans.
3. **Occasion** — presets from `GET /occasions` as evocative, keyboard-navigable
   cards (music style, pacing, aspect ratio) with per-occasion gradients.
4. **Generate** — the real photo bytes are streamed to
   `POST /reels/upload-multipart` (multipart/form-data) so the pipeline animates,
   stitches, stores and seals *your* pixels; if no photos were selected it falls
   back to the synthetic `POST /reels` path. Either way the UI shows a rich,
   honest pipeline progress (photos → clips → bridges → music-cuts → stitch → B2
   → provenance) with full error/retry handling.
5. **Result** — video player (graceful cinematic poster when the offline/degrade
   path returns a `b2://` URL), a **Provenance** panel (SHA-256 manifest seal,
   storage badge, per-step Genblaze hashes from `GET /reels/{name}`), and
   Share/Download + platform deep-links.

Every state — loading, empty, error(retry), success — is designed. Fully
responsive (mobile → desktop), accessible (labels, focus rings, radiogroup
semantics, `aria-*`), with restrained motion.

## Develop

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

`npm run dev` proxies the API routes (`/health`, `/occasions`, `/reels`) to
`VITE_DEV_PROXY_TARGET` (defaults to the live Cloud Run service) so the browser
sees a single origin and there is **no CORS**. To develop against a local
backend: `VITE_DEV_PROXY_TARGET=http://localhost:8000 npm run dev` alongside
`uvicorn cinemory.api:app --reload`.

Config: copy `.env.example` → `.env.local`. Nothing here is secret (all `VITE_`
vars are public/embedded).

## Quality gates

```bash
npm run typecheck    # tsc --noEmit (strict)
npm run test         # vitest (api zod-validation, utils, components)
npm run build        # tsc + vite build -> dist/
```

## How the API is wired

- Typed client in `src/lib/api.ts` — every response is validated at runtime with
  **Zod**; `POST /reels` is synchronous (no polling), `GET /reels/{name}` returns
  the sealed manifest (both the offline fake and the live B2 adapter keep a
  queryable run index), and any lookup miss is treated as `null`.
- Data fetching via **React Query** hooks (`src/lib/queries.ts`).
- Base URL = `import.meta.env.VITE_API_BASE ?? ""`. Empty in production →
  relative paths → Firebase rewrites to Cloud Run (see repo-root `firebase.json`).

## Deploy (Firebase Hosting + Cloud Run proxy)

The BFF/single-origin pattern: Firebase serves this SPA and rewrites the API
routes to the Cloud Run `cinemory` service (`europe-west1`) — no CORS, and
`cinemory.ai` maps to the apex trivially.

```bash
cd frontend && npm run build      # outputs frontend/dist/
cd ..                             # repo root (firebase.json lives here)
firebase login                    # INTERACTIVE — run this yourself
firebase use upgradegr-cinemory   # confirm/adjust in .firebaserc
firebase deploy --only hosting
```

> **Important:** the Firebase project in `.firebaserc` (`upgradegr-cinemory`)
> **must be the same GCP project that hosts the Cloud Run `cinemory` service**
> (region `europe-west1`, a Firebase-supported Cloud Run rewrite region) — the
> Hosting → Cloud Run rewrite only resolves within one project. Confirm/adjust
> the project id before deploying. `firebase.json` is strict JSON (no comments);
> the rewrite **order matters** — the API routes are listed before the `**` SPA
> fallback because Firebase uses first-match.

The Cloud Run container serves the API **and this same React client**: the
Dockerfile builds `frontend/` (Vite) into the image's static dir, so one
container ships both. Firebase Hosting serves the identical client and rewrites
the API routes to Cloud Run. The legacy `web/` client is kept as a reference
(still type-checked/built in CI) but is **not** served by the container. See
repo `README.md` and `deploy/CLOUDRUN.md` for the backend.
