// One-click demo storyboard: deterministic, client-side sample "photos".
//
// A judge without photos on hand should reach the money screen in under a
// minute, so this module paints a small synthetic set — warm, cinematic
// gradient scenes in the app's gold/dark identity — straight onto a canvas and
// hands back real `File` objects. They flow through the EXACT same store and
// upload path as user-picked files (multipart bytes, storage, provenance);
// nothing downstream knows they are synthetic. Zero bundled assets, zero
// licensing: every pixel is generated here, deterministically (seeded PRNG),
// and each frame is labelled "Sample n" so screenshots stay honest.

type Scene = "dawn" | "ridge" | "coast" | "lanterns" | "bokeh";

export interface SamplePhotoSpec {
  /** Honest on-image label, e.g. "Sample 1". */
  label: string;
  filename: string;
  seed: number;
  scene: Scene;
  /** Human, content-describing alt text (screen readers; never the filename). */
  description: string;
}

export const SAMPLE_PHOTO_COUNT = 5;

const SCENES: ReadonlyArray<Scene> = ["dawn", "ridge", "coast", "lanterns", "bokeh"];

/** Content-describing alt text per scene — what the picture actually depicts. */
const SCENE_DESCRIPTION: Record<Scene, string> = {
  dawn: "A cinematic dawn breaking in gold over layered dark hills",
  ridge: "Warm sunset glow behind a silhouetted mountain ridge",
  coast: "Golden-hour light shimmering across a calm coastline",
  lanterns: "Paper lanterns rising into a starlit night sky",
  bokeh: "Soft, warm out-of-focus bokeh lights in cinematic tones",
};

/** The deterministic storyboard: same specs (order, seeds, scenes) every call. */
export function samplePhotoSpecs(): SamplePhotoSpec[] {
  return SCENES.map((scene, i) => ({
    label: `Sample ${i + 1}`,
    filename: `cinemory-sample-${i + 1}.png`,
    // Fixed per-frame seeds → byte-stable art across clicks and sessions.
    seed: 0xc1e0 + i * 7919,
    scene,
    description: SCENE_DESCRIPTION[scene],
  }));
}

/** Descriptive alt strings, aligned to `generateSamplePhotos()` order. */
export function samplePhotoAlts(): string[] {
  return samplePhotoSpecs().map((s) => s.description);
}

/** Deterministic PRNG (mulberry32) — the standard tiny seeded generator. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const W = 1280;
const H = 720;

// Cinemory palette (tailwind gold/ember/ink tokens, hex-inlined for canvas).
const GOLD = "#d8b25a";
const GOLD_SOFT = "#e8cd8c";
const EMBER = "#e2543a";
const INK = "#0b0a12";
const INK_WARM = "#221527";

type Ctx = CanvasRenderingContext2D;

function skyGradient(ctx: Ctx, stops: Array<[number, string]>): void {
  const g = ctx.createLinearGradient(0, 0, 0, H);
  for (const [at, color] of stops) g.addColorStop(at, color);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
}

function sunDisc(ctx: Ctx, x: number, y: number, r: number, color: string): void {
  const glow = ctx.createRadialGradient(x, y, r * 0.2, x, y, r * 3.2);
  glow.addColorStop(0, `${color}cc`);
  glow.addColorStop(1, `${color}00`);
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

function ridge(ctx: Ctx, rand: () => number, baseY: number, amp: number, color: string): void {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.moveTo(0, H);
  ctx.lineTo(0, baseY);
  const segments = 7;
  for (let s = 1; s <= segments; s += 1) {
    const x = (W / segments) * s;
    const y = baseY - amp * (0.25 + rand() * 0.75) * (s % 2 === 0 ? 0.55 : 1);
    ctx.lineTo(x, y);
  }
  ctx.lineTo(W, H);
  ctx.closePath();
  ctx.fill();
}

function vignette(ctx: Ctx): void {
  const g = ctx.createRadialGradient(W / 2, H / 2, H * 0.42, W / 2, H / 2, H * 0.95);
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, "rgba(0,0,0,0.55)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
}

function labelChip(ctx: Ctx, label: string): void {
  ctx.font = "500 26px system-ui, sans-serif";
  const padX = 18;
  const textW = ctx.measureText(label).width;
  const w = textW + padX * 2;
  const h = 46;
  const x = W - w - 28;
  const y = H - h - 26;
  ctx.fillStyle = "rgba(8,8,14,0.62)";
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, 23);
  ctx.fill();
  ctx.fillStyle = "rgba(232,205,140,0.92)"; // gold-soft
  ctx.textBaseline = "middle";
  ctx.fillText(label, x + padX, y + h / 2 + 1);
}

function drawScene(ctx: Ctx, spec: SamplePhotoSpec): void {
  const rand = mulberry32(spec.seed);
  switch (spec.scene) {
    case "dawn": {
      skyGradient(ctx, [
        [0, INK],
        [0.55, "#3a2033"],
        [0.8, "#8a4a3a"],
        [1, GOLD],
      ]);
      sunDisc(ctx, W * 0.5, H * 0.74, 64, GOLD_SOFT);
      ridge(ctx, rand, H * 0.8, 70, "#160f1d");
      ridge(ctx, rand, H * 0.9, 46, "#0c0812");
      break;
    }
    case "ridge": {
      skyGradient(ctx, [
        [0, "#120c1a"],
        [0.6, "#4a2438"],
        [1, "#b06a3c"],
      ]);
      sunDisc(ctx, W * 0.72, H * 0.62, 46, EMBER);
      ridge(ctx, rand, H * 0.66, 110, "#241329");
      ridge(ctx, rand, H * 0.78, 90, "#170d1c");
      ridge(ctx, rand, H * 0.9, 60, "#0b0710");
      break;
    }
    case "coast": {
      skyGradient(ctx, [
        [0, "#191021"],
        [0.5, "#67333a"],
        [0.62, "#c07a44"],
        [0.63, "#2a1a2e"],
        [1, INK],
      ]);
      sunDisc(ctx, W * 0.35, H * 0.56, 42, GOLD_SOFT);
      // Sun path shimmering on the water: short horizontal strokes.
      for (let s = 0; s < 42; s += 1) {
        const y = H * 0.65 + (H * 0.32 * s) / 42 + rand() * 6;
        const len = 30 + rand() * 130 * (1 - s / 60);
        ctx.fillStyle = `rgba(232,205,140,${0.28 * (1 - s / 48)})`;
        ctx.fillRect(W * 0.35 - len / 2 + (rand() - 0.5) * 60, y, len, 3);
      }
      break;
    }
    case "lanterns": {
      skyGradient(ctx, [
        [0, INK],
        [0.7, INK_WARM],
        [1, "#41213a"],
      ]);
      // Stars.
      for (let s = 0; s < 90; s += 1) {
        ctx.fillStyle = `rgba(255,255,255,${0.25 + rand() * 0.5})`;
        const r = rand() < 0.12 ? 2 : 1;
        ctx.fillRect(rand() * W, rand() * H * 0.55, r, r);
      }
      sunDisc(ctx, W * 0.78, H * 0.2, 34, "#e6e0d2"); // moon
      // Rising paper lanterns.
      for (let s = 0; s < 16; s += 1) {
        const x = rand() * W;
        const y = H * 0.3 + rand() * H * 0.62;
        const r = 5 + rand() * 11;
        const g = ctx.createRadialGradient(x, y, 1, x, y, r * 3);
        g.addColorStop(0, "rgba(232,166,80,0.9)");
        g.addColorStop(1, "rgba(232,166,80,0)");
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, r * 3, 0, Math.PI * 2);
        ctx.fill();
      }
      ridge(ctx, rand, H * 0.92, 40, "#070510");
      break;
    }
    case "bokeh": {
      skyGradient(ctx, [
        [0, "#0e0913"],
        [1, "#2b1420"],
      ]);
      // Large out-of-focus warm highlights.
      for (let s = 0; s < 26; s += 1) {
        const x = rand() * W;
        const y = rand() * H;
        const r = 26 + rand() * 90;
        const warm = rand();
        const color =
          warm < 0.5 ? "216,178,90" : warm < 0.8 ? "226,84,58" : "232,205,140";
        const g = ctx.createRadialGradient(x, y, r * 0.5, x, y, r);
        g.addColorStop(0, `rgba(${color},${0.1 + rand() * 0.2})`);
        g.addColorStop(0.85, `rgba(${color},${0.14 + rand() * 0.18})`);
        g.addColorStop(1, `rgba(${color},0)`);
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
  }
  vignette(ctx);
  labelChip(ctx, spec.label);
}

function canvasToPngFile(canvas: HTMLCanvasElement, filename: string): Promise<File> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error("Canvas could not encode a PNG in this browser."));
        return;
      }
      resolve(new File([blob], filename, { type: "image/png" }));
    }, "image/png");
  });
}

/** Paint the deterministic sample set and return real `File` objects, ready
 *  for the exact same `addPhotos` → multipart upload path as user files. */
export async function generateSamplePhotos(
  doc: Document = document,
): Promise<File[]> {
  const files: File[] = [];
  for (const spec of samplePhotoSpecs()) {
    const canvas = doc.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D is not supported in this browser.");
    drawScene(ctx, spec);
    files.push(await canvasToPngFile(canvas, spec.filename));
  }
  return files;
}
