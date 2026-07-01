// Minimal browser entry: request a synthetic demo reel and render its
// provenance. The heavy React/Next UI is a deploy-time concern (see README);
// this file exists so the web client is real, typechecked, and SAST-scanned.
import { CinemoryClient, type ReelResponse } from "./lib/api.js";

const API_BASE = (globalThis as { CINEMORY_API?: string }).CINEMORY_API ?? "";

async function generateDemoReel(client: CinemoryClient): Promise<ReelResponse> {
  const health = await client.health();
  if (health.status !== "ok") {
    throw new Error(`API not healthy: ${health.status}`);
  }
  return client.createReel({ name: "demo-reel", chapters: 3, per_chapter: 2 });
}

export async function main(): Promise<void> {
  const client = new CinemoryClient(API_BASE);
  const reel = await generateDemoReel(client);
  const out = document.getElementById("output");
  if (out) {
    out.textContent = `Reel ${reel.reel_name} sealed with manifest ${reel.manifest_hash}`;
  }
}

export { generateDemoReel };
