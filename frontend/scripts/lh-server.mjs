// Static server for Lighthouse CI: serves frontend/dist AND answers the two API
// routes the app calls on load (/health on the landing, /occasions on the
// occasion step) so a spurious 404 never dings the best-practices score. No
// dependencies — plain node http. Paths resolve via import.meta.url, so it works
// regardless of the current working directory.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { extname, join } from "node:path";

const DIST = fileURLToPath(new URL("../dist/", import.meta.url));
const PORT = Number(process.env.LH_PORT || 4179);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

const OCCASIONS = {
  occasions: [
    { key: "anniversary", label: "Anniversary", music_style: "warm acoustic", tempo: 84, seconds_per_clip: 4, transition: "cross-dissolve", title_style: "elegant serif", aspect_ratio: "16:9" },
    { key: "wedding", label: "Wedding", music_style: "cinematic emotional piano", tempo: 88, seconds_per_clip: 4, transition: "slow film-dissolve", title_style: "fine script", aspect_ratio: "16:9" },
    { key: "graduation", label: "Graduation", music_style: "triumphant strings", tempo: 96, seconds_per_clip: 3, transition: "whip-pan", title_style: "bold display", aspect_ratio: "16:9" },
    { key: "birthday", label: "Birthday", music_style: "bright indie pop", tempo: 120, seconds_per_clip: 3, transition: "punch-in", title_style: "playful rounded", aspect_ratio: "9:16" },
    { key: "year-in-review", label: "Year in Review", music_style: "driving synth", tempo: 128, seconds_per_clip: 2, transition: "hard cut", title_style: "kinetic sans", aspect_ratio: "16:9" },
    { key: "business-event", label: "Business Event", music_style: "polished corporate", tempo: 100, seconds_per_clip: 3, transition: "clean slide", title_style: "premium grotesk", aspect_ratio: "16:9" },
  ],
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || "/", `http://localhost:${PORT}`);
  const p = url.pathname;
  if (p === "/health") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify({ status: "ok", service: "cinemory", mode: "offline" }));
  }
  if (p === "/occasions") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(JSON.stringify(OCCASIONS));
  }
  const rel = p === "/" ? "index.html" : p.replace(/^\/+/, "");
  try {
    const body = await readFile(join(DIST, rel));
    res.writeHead(200, { "content-type": MIME[extname(rel)] || "application/octet-stream" });
    return res.end(body);
  } catch {
    // SPA fallback.
    const html = await readFile(join(DIST, "index.html"));
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    return res.end(html);
  }
});

server.listen(PORT, () => console.log(`LH server running on http://localhost:${PORT}`));
