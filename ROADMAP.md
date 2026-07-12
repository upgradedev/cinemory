# Cinemory Roadmap

> **Canonical repo:** [github.com/upgradedev/cinemory](https://github.com/upgradedev/cinemory)
> is the live Cinemory codebase (local working copy: `repos/cinemory`).

Cinemory turns a set of photos into a scored, provenance-sealed cinematic video
reel. The hackathon-judged core is deliberately **offline and PII-safe**: the
default demo and all of CI run on **synthetic** photos ([`synthetic.py`](src/cinemory/synthetic.py))
with zero credentials. Everything below layers *opt-in, consent-gated* reach on
top of that core — never in CI, never in the default demo, no real photos or
keys ever committed.

---

## ✅ Implemented (this milestone)

### 1. Web Share share-sheet + export — `frontend/` (+ legacy `web/` reference)
- Native share sheet via the **Web Share API** (`navigator.share({ files: [reel.mp4] })`)
  — reaches Instagram, Facebook, LinkedIn, YouTube and every installed target
  with **zero platform API review**.
- **Download-to-`.mp4`** export button (share-sheet fallback / desktop).
- **Per-platform deep-links** (Facebook + LinkedIn share-by-URL; Instagram +
  YouTube app/Studio deep-links) as a universal fallback.
- Pure, dependency-injectable helpers — shipped in the product UI at
  [`frontend/src/lib/share.ts`](frontend/src/lib/share.ts) (the original
  reference implementation also lives in the legacy `web/` SPA at
  [`web/src/lib/share.ts`](web/src/lib/share.ts)); typecheck-clean; no new
  runtime npm deps.

### 2. Occasion templates / themes — config-driven
- Six selectable presets — **anniversary, graduation, birthday, wedding,
  year-in-review, business-event/award-ceremony** — each adjusting scene labels,
  prompt direction, music mood, pacing and aspect ratio
  ([`occasions.py`](src/cinemory/occasions.py)).
- **Config-driven:** add one `Occasion` dict entry to add a new theme — nothing
  else changes. Slash-named/aliased keys (`award-ceremony`) resolve to a
  canonical key.
- Surfaced on the CLI (`--occasion`), the API (`GET /occasions`, `POST /reels`
  `occasion` field), and the web selector. The chosen occasion is recorded in
  the **sealed provenance manifest**.

### 3. Google Photos **Picker API** connector — opt-in, consented
- Full Picker flow ([`connectors/google_photos.py`](src/cinemory/connectors/google_photos.py)):
  OAuth consent → create Picker session → user hand-picks in Google's own UI →
  poll the session → list picked items → download the short-lived `baseUrl`
  bytes (`baseUrl=d`).
- **Why Picker, not Library:** Google removed the broad library-read scopes, so
  "auto-curate the whole library" is impossible. Picker is the sanctioned path —
  the app only ever sees the items the user explicitly picks.

### 4. YouTube upload + LinkedIn share — opt-in, API
- **YouTube** ([`connectors/youtube.py`](src/cinemory/connectors/youtube.py)):
  Data API v3 **resumable** `videos.insert` (init session → PUT bytes → video
  resource).
- **LinkedIn** ([`connectors/linkedin.py`](src/cinemory/connectors/linkedin.py)):
  `/rest/posts` link share, plus native video upload (initialize → PUT →
  finalize → post).

> **Testing guarantee.** Every connector talks to an injectable HTTP transport
> seam ([`connectors/_http.py`](src/cinemory/connectors/_http.py)). The offline
> tests script a **fake transport**, so the multi-step flows are verified with
> no network, no third-party HTTP import, no credentials and no real photos. The
> package imports cleanly in CI with none of the live extras installed. See
> [`tests/integration/test_connectors.py`](tests/integration/test_connectors.py).

---

## 🚫 Not implemented — show-stoppers (by design)

### Apple / iCloud server connector — **no server API exists**
There is **no third-party server-side API** to read a user's iCloud Photos. The
only sanctioned path is a **native iOS app using PhotoKit** (on-device, with the
user's permission). Cinemory therefore relies on the mobile **`<input type=file>`**
picker, which on iOS already streams the iCloud original bytes into the browser —
so users on iPhone can already contribute their photos today. A native
PhotoKit iOS app is the only route to deeper Apple integration and is tracked as
a separate, future native-client effort.

### Personal Instagram / Facebook auto-post — **Graph API is Business/Creator-only**
Meta's Graph API only allows programmatic publishing from **Business/Creator**
accounts (via a connected Facebook Page), not personal profiles. Auto-posting to
a *personal* IG/FB feed is not permitted by the platform. This is fully covered
by the **Web Share share-sheet** (feature 1), which posts to personal IG/FB
through the OS share flow with no API at all.

---

## 🧭 Go-live steps for the opt-in connectors (user / lead-time)

These are the exact steps to switch the opt-in features from "flow implemented +
offline-tested" to "live". None affect CI or the default demo.

**Install the live dependency**
```bash
pip install 'cinemory[connectors]'   # adds `requests` for the live transport
```

**A. Google Photos Picker (OAuth app verification — has lead time)**
1. In **Google Cloud Console** → create/confirm a project → enable the
   **Photos Picker API**.
2. **OAuth consent screen:** set app type *External*, add the scope
   `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`
   (a **sensitive scope**), and add your logo/privacy-policy/domain.
3. **Submit for verification.** Until Google approves, only **test users** you
   add on the consent screen can consent — plan for the review lead time.
4. Create an **OAuth client ID** (Web) → set `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` in `.env`.
5. Run the consent flow (`GoogleOAuth.authorization_url` → user consents →
   `exchange_code`) to obtain the access token used by `GooglePhotosPicker`.

**B. YouTube upload (same Google project + audit caveat)**
1. Enable the **YouTube Data API v3** on the same project; add scope
   `https://www.googleapis.com/auth/youtube.upload`.
2. **Unverified-app caveat:** until the OAuth app passes Google's
   verification/**audit**, uploads are **forced to `privacyStatus=private`** and
   subject to a **daily upload cap**. Public/unlisted at scale requires the
   audit. (Cinemory defaults uploads to `private` for this reason.)
3. Use the same OAuth token (with the upload scope granted) for
   `YouTubeUploader`.

**C. LinkedIn share (API product approval)**
1. Create a **LinkedIn Developer app** linked to a company page.
2. Request the product you need — **"Share on LinkedIn"** (`w_member_social`,
   member posts) and/or the **Community Management API** (organization posts).
   Both require **LinkedIn review/approval**.
3. Complete OAuth to obtain an access token; set `LINKEDIN_ACCESS_TOKEN` and
   `LINKEDIN_AUTHOR_URN` (`urn:li:person:{id}` for a member, or
   `urn:li:organization:{id}` for a company page — the latter needs an admin
   role). The REST API is date-versioned (`LinkedIn-Version` header).

> Endpoint paths and scope strings in the connectors follow current docs but
> should be **re-confirmed against the live API docs when credentials are
> added** — the same convention the Genblaze adapter uses.

---

## 🔭 Strategic direction

### B2B business-events wedge
The `business-event/award-ceremony` occasion is more than another theme — it is
a **go-to-market wedge**. Conferences, award ceremonies, sales kick-offs and
company milestones generate large volumes of photos that a marketing/comms team
needs turned into a branded highlight reel **fast, repeatably, and with clear
rights/provenance**. That audience:
- has budget and a recurring need (every event),
- values the **LinkedIn share** and **branded occasion styling** paths directly,
- and cares about **provenance** for brand-safety and rights tracking.
This is a cleaner initial monetization path than pure consumer virality, and it
reuses the same pipeline.

### C2PA provenance — standardizing what Cinemory already does
Cinemory already seals every reel with a **SHA-256 content-addressed manifest**
(provider, model, prompt, params, timestamps, every asset hash), persisted and
embedded in the container and re-verifiable offline
([`provenance.py`](src/cinemory/provenance.py)). **C2PA** (the Coalition for
Content Provenance and Authenticity) is the **industry-standard evolution of
exactly this** — cryptographically signed Content Credentials for AI-generated
and edited media. The roadmap is to express the existing manifest as a **C2PA
manifest** (signed claim + assertions) so provenance is interoperable with the
broader ecosystem (Adobe, camera makers, platforms) rather than a bespoke
format — a natural upgrade, not a rebuild, and a strong differentiator for the
B2B/brand-safety wedge above.
