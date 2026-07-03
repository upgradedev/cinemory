// Browser entry: pick an occasion, request a synthetic demo reel, render its
// provenance, and expose the reel via the native share sheet + download +
// per-platform deep-links. The heavy React/Next UI is a deploy-time concern
// (see README); this file keeps the web client real, typechecked and
// SAST-scanned.
import { CinemoryClient, type Occasion, type ReelResponse } from "./lib/api.js";
import {
  downloadReel,
  fetchReelFile,
  platformDeepLinks,
  reelFilename,
  shareReel,
} from "./lib/share.js";

const API_BASE = (globalThis as { CINEMORY_API?: string }).CINEMORY_API ?? "";

function byId<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

async function loadOccasions(client: CinemoryClient): Promise<Occasion[]> {
  const select = byId<HTMLSelectElement>("occasion");
  const occasions = await client.occasions();
  if (select) {
    select.innerHTML = "";
    for (const o of occasions) {
      const opt = document.createElement("option");
      opt.value = o.key;
      opt.textContent = `${o.label} — ${o.music_style}`;
      select.appendChild(opt);
    }
  }
  return occasions;
}

function selectedOccasion(): string {
  return byId<HTMLSelectElement>("occasion")?.value ?? "anniversary";
}

async function generateDemoReel(client: CinemoryClient): Promise<ReelResponse> {
  const health = await client.health();
  if (health.status !== "ok") throw new Error(`API not healthy: ${health.status}`);
  return client.createReel({
    name: "demo-reel",
    chapters: 3,
    per_chapter: 2,
    occasion: selectedOccasion(),
  });
}

/** Wire the share sheet / download / deep-link controls for a finished reel. */
function renderShareControls(reel: ReelResponse): void {
  const shareBtn = byId<HTMLButtonElement>("share");
  const downloadBtn = byId<HTMLButtonElement>("download");
  const links = byId<HTMLDivElement>("deeplinks");
  const status = byId<HTMLElement>("share-status");
  const filename = reelFilename(reel.reel_name);
  // Only http(s) reel URLs are fetchable in the browser (live B2). The offline
  // demo returns a b2:// URL, so share/download stay disabled with a hint.
  const fetchable = !!reel.reel_url && /^https?:\/\//i.test(reel.reel_url);
  const pageUrl = reel.reel_url ?? (typeof location !== "undefined" ? location.href : "");

  const meta = {
    title: `Cinemory — ${reel.reel_name}`,
    text: "A cinematic memory reel, sealed with verifiable provenance.",
    pageUrl,
  };

  if (shareBtn) {
    shareBtn.disabled = !fetchable;
    shareBtn.onclick = async () => {
      if (!reel.reel_url) return;
      try {
        const file = await fetchReelFile(reel.reel_url, filename);
        const outcome = await shareReel(file, meta);
        if (status) {
          status.textContent =
            outcome === "unsupported"
              ? "Native share unavailable here — use Download or the platform links below."
              : `Share ${outcome}.`;
        }
      } catch (e) {
        if (status) status.textContent = `Share failed: ${String(e)}`;
      }
    };
  }

  if (downloadBtn) {
    downloadBtn.disabled = !fetchable;
    downloadBtn.onclick = async () => {
      if (!reel.reel_url) return;
      const file = await fetchReelFile(reel.reel_url, filename);
      downloadReel(file, filename);
    };
  }

  if (links) {
    const dl = platformDeepLinks(pageUrl);
    links.innerHTML = "";
    for (const [name, href] of Object.entries(dl)) {
      const a = document.createElement("a");
      a.href = href;
      a.textContent = name;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.style.marginRight = "0.75rem";
      links.appendChild(a);
    }
  }

  if (status && !fetchable) {
    status.textContent =
      "Offline demo: reel stored at " +
      `${reel.reel_url ?? "(none)"}. Share/Download activate on the live B2 path.`;
  }
}

export async function main(): Promise<void> {
  const client = new CinemoryClient(API_BASE);
  const reel = await generateDemoReel(client);
  const out = byId<HTMLElement>("output");
  if (out) {
    out.textContent =
      `Reel ${reel.reel_name} (${reel.occasion ?? "anniversary"}) ` +
      `sealed with manifest ${reel.manifest_hash}`;
  }
  renderShareControls(reel);
}

export { generateDemoReel, loadOccasions, renderShareControls };
