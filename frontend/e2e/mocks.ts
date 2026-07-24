import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { Page } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));

// The golden manifest is the VERBATIM raw HTTP body the real backend serves for
// GET /reels/{name} (offline mode); its bytes hash to the sealed manifest_hash
// below. Serving these exact bytes means the in-browser verifier recomputes the
// same SHA-256 and the Verify button lands on "Verified ✓" — a real, honest
// outcome, not a stub. We read the file as bytes and never re-serialize it, so
// the hash stays byte-exact.
const GOLDEN_MANIFEST_BYTES = readFileSync(
  resolve(__dirname, "../src/test/fixtures/golden-manifest.json"),
);
export const GOLDEN_MANIFEST_HASH =
  "06a6f25193bd5c05e4b64059793c03bda8400bc35f42eada29a7673ccf819060";

const OCCASIONS = {
  occasions: [
    { key: "anniversary", label: "Anniversary", music_style: "warm acoustic",
      tempo: 84, seconds_per_clip: 4, transition: "cross-dissolve",
      title_style: "elegant serif", aspect_ratio: "16:9" },
    { key: "wedding", label: "Wedding", music_style: "cinematic emotional piano",
      tempo: 88, seconds_per_clip: 4, transition: "slow film-dissolve",
      title_style: "fine script", aspect_ratio: "16:9" },
    { key: "graduation", label: "Graduation", music_style: "triumphant strings",
      tempo: 96, seconds_per_clip: 3, transition: "whip-pan",
      title_style: "bold display", aspect_ratio: "16:9" },
    { key: "birthday", label: "Birthday", music_style: "bright indie pop",
      tempo: 120, seconds_per_clip: 3, transition: "punch-in",
      title_style: "playful rounded", aspect_ratio: "9:16" },
    { key: "year-in-review", label: "Year in Review", music_style: "driving synth",
      tempo: 128, seconds_per_clip: 2, transition: "hard cut",
      title_style: "kinetic sans", aspect_ratio: "16:9" },
    { key: "business-event", label: "Business Event", music_style: "polished corporate",
      tempo: 100, seconds_per_clip: 3, transition: "clean slide",
      title_style: "premium grotesk", aspect_ratio: "16:9" },
  ],
};

// The sealed reel the mocked POST returns. provider_degraded keeps the result
// on the honest slideshow path (no <video> element → no 404 request that would
// dock Lighthouse best-practices), and manifest_hash matches the golden bytes so
// in-browser Verify succeeds.
const REEL_RESPONSE = {
  reel_name: "cinemory-reel",
  occasion: "wedding",
  reel_url: "b2://cinemory-demo/cinemory-reel/reel.mp4",
  playback_url: null,
  reel_sha256: "2cbb384a8b75ca4ed732e6b1d713f532bcb90149b95f0e8c4a2823afa36da8bb",
  manifest_uri: "b2://cinemory-demo/cinemory-reel/manifest.json",
  manifest_hash: GOLDEN_MANIFEST_HASH,
  steps: 4,
  provider: "fake-genblaze",
  provider_degraded: true,
  degrade_reason: "Live AI generation is not wired in this preview build.",
};

// The server-side aggregate re-verification receipt returned by
// GET /reels/{name}/verify (src/cinemory/provenance.py::verify_all). All checks
// pass, so the ProvenancePanel renders "N/N checks passed — all verified" — the
// honest offline outcome for the byte-exact golden reel.
function check(id: string, label: string) {
  return { id, label, passed: true, evidence: `${label} — re-verified from stored bytes` };
}
const VERIFY_RECEIPT = {
  success: true,
  digest: "b".repeat(64),
  checks: [
    check("seal.manifest_hash", "Manifest seal recomputes (SHA-256)"),
    check("artifact.reel", "Reel bytes match the sealed hash"),
    check("artifact.provenance_reel", "Provenance-reel wraps the sealed reel"),
    check("artifact.clip.0", "Step 0 clip bytes match the sealed hash"),
    check("artifact.clip.1", "Step 1 clip bytes match the sealed hash"),
    check("artifact.clip.2", "Step 2 clip bytes match the sealed hash"),
    check("artifact.clip.3", "Step 3 clip bytes match the sealed hash"),
    check("structural.embedded_manifest", "Embedded manifest equals the standalone manifest"),
    check("structural.step_assets_present", "Every step asset resolves in the store"),
    check("structural.source_citation", "Every step cites resolvable source photos"),
    check("structural.provider_model", "Every step names a provider and model"),
  ],
};

/**
 * Intercept every Cinemory API route so the journey runs with no backend.
 * Covers /health, /occasions, POST /reels(+upload variants) and GET
 * /reels/{name}. Registered on the browser context so it also applies to any
 * pages the app opens.
 */
export async function mockCinemoryApi(page: Page): Promise<void> {
  await page.route("**/health", (route) =>
    route.fulfill({
      json: { status: "ok", service: "cinemory", mode: "offline" },
    }),
  );

  await page.route("**/occasions", (route) => route.fulfill({ json: OCCASIONS }));

  // The server-side re-verification receipt (GET /reels/{name}/verify). Declared
  // BEFORE the /reels catch-all and also excluded from it, so the aggregate
  // receipt is never masked by the manifest handler regardless of route order.
  await page.route(
    (url) => url.pathname.startsWith("/reels/") && url.pathname.endsWith("/verify"),
    (route) => route.fulfill({ json: VERIFY_RECEIPT }),
  );

  // One handler for the rest of the /reels surface: POST (any create/upload
  // variant) returns the sealed reel; GET /reels/{name} returns the byte-exact
  // golden manifest so the in-browser seal verification is real.
  await page.route(
    (url) =>
      url.pathname === "/reels" ||
      (url.pathname.startsWith("/reels/") && !url.pathname.endsWith("/verify")),
    async (route) => {
      if (route.request().method() === "POST") {
        // A delay so the transient "generate" step is stably observable (the
        // axe scan and the opacity poll must not race the auto-advance to the
        // result) even on a slow CI runner; mirrors real render latency.
        await new Promise((r) => setTimeout(r, 1500));
        return route.fulfill({ json: REEL_RESPONSE });
      }
      return route.fulfill({
        contentType: "application/json",
        body: GOLDEN_MANIFEST_BYTES,
      });
    },
  );
}
