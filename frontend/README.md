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
   tasteful empty state. Photos stay on-device; their count/order shapes the reel.
3. **Occasion** — presets from `GET /occasions` as evocative, keyboard-navigable
   cards (music style, pacing, aspect ratio) with per-occasion gradients.
4. **Generate** — `POST /reels` with a rich, honest pipeline progress
   (photos → clips → bridges → music-cuts → stitch → B2 → provenance), full
   error/retry handling.
5. **Result** — video player (graceful cinematic poster when the offline demo
   returns a `b2://` URL), a **Provenance** panel (SHA-256 manifest seal,
   "Stored on Backblaze B2" badge, per-step Genblaze hashes from
   `GET /reels/{name}`), and Share/Download + platform deep-links.

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
  the sealed manifest (offline/indexed store) and is treated as `null` on the
  live-path 404.
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

Cloud Run (the API + the original `web/` fallback UI) is unchanged and keeps
working; Firebase now serves the premium client. See repo `README.md` and
`deploy/CLOUDRUN.md` for the backend.
