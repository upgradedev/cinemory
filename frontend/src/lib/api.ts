// Typed Cinemory API client with runtime Zod validation of every response.
//
// Base URL contract (see vite.config.ts + firebase.json):
//   • Production: VITE_API_BASE is empty → relative paths → Firebase Hosting
//     rewrites `/health`, `/occasions`, `/reels/**` to the Cloud Run service.
//     Single origin, zero CORS.
//   • Dev: relative paths hit the Vite dev server, which proxies the same
//     routes to VITE_API_BASE (the Cloud Run URL). Same-origin illusion, no CORS.
//   • Escape hatch: if you set VITE_API_BASE to an absolute URL it is used
//     directly (requires the backend to allow that origin).
import { z } from "zod";

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

// ── Schemas ──────────────────────────────────────────────────────────────────

export const HealthSchema = z.object({
  status: z.string(),
  service: z.string(),
  mode: z.string(),
});
export type Health = z.infer<typeof HealthSchema>;

export const OccasionSchema = z.object({
  key: z.string(),
  label: z.string(),
  music_style: z.string(),
  tempo: z.number(),
  seconds_per_clip: z.number(),
  transition: z.string(),
  title_style: z.string(),
  aspect_ratio: z.string(),
});
export type Occasion = z.infer<typeof OccasionSchema>;

const OccasionsResponseSchema = z.object({ occasions: z.array(OccasionSchema) });

export const ReelRequestSchema = z.object({
  name: z.string(),
  chapters: z.number().int().positive(),
  per_chapter: z.number().int().positive(),
  occasion: z.string(),
});
export type ReelRequest = z.infer<typeof ReelRequestSchema>;

export const ReelResponseSchema = z.object({
  reel_name: z.string(),
  occasion: z.string().optional(),
  reel_url: z.string().nullable(),
  reel_sha256: z.string(),
  manifest_uri: z.string().nullable(),
  manifest_hash: z.string(),
  steps: z.number().int(),
});
export type ReelResponse = z.infer<typeof ReelResponseSchema>;

// Full provenance manifest (GET /reels/{name}) — offline/indexed store only.
export const AssetSchema = z.object({
  modality: z.string(),
  sha256: z.string(),
  size_bytes: z.number(),
  url: z.string().nullable().optional(),
  filename: z.string().nullable().optional(),
});
export type Asset = z.infer<typeof AssetSchema>;

export const StepSchema = z.object({
  provider: z.string(),
  model: z.string(),
  prompt: z.string(),
  modality: z.string(),
  params: z.record(z.unknown()).default({}),
  started_at: z.string(),
  finished_at: z.string(),
  asset: AssetSchema,
});
export type Step = z.infer<typeof StepSchema>;

export const ManifestSchema = z.object({
  schema: z.string(),
  reel_name: z.string(),
  occasion: z.string(),
  occasion_style: z.record(z.unknown()).default({}),
  reel_asset: AssetSchema,
  steps: z.array(StepSchema),
  manifest_hash: z.string(),
});
export type Manifest = z.infer<typeof ManifestSchema>;

// ── Errors ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Client ───────────────────────────────────────────────────────────────────

async function request<S extends z.ZodTypeAny>(
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (err) {
    throw new ApiError("Network unreachable — check your connection.", undefined, err);
  }
  if (!res.ok) {
    throw new ApiError(`Request to ${path} failed (${res.status}).`, res.status);
  }
  let json: unknown;
  try {
    json = await res.json();
  } catch (err) {
    throw new ApiError(`Malformed response from ${path}.`, res.status, err);
  }
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    throw new ApiError(
      `Unexpected response shape from ${path}.`,
      res.status,
      parsed.error,
    );
  }
  return parsed.data;
}

export const cinemoryApi = {
  health(): Promise<Health> {
    return request("/health", HealthSchema);
  },

  async occasions(): Promise<Occasion[]> {
    const { occasions } = await request("/occasions", OccasionsResponseSchema);
    return occasions;
  },

  createReel(body: ReelRequest): Promise<ReelResponse> {
    return request("/reels", ReelResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  /** Fetch the full sealed manifest. Returns null when the store is not
   *  indexed (the live B2 path returns 404 by design). */
  async manifest(name: string): Promise<Manifest | null> {
    try {
      return await request(`/reels/${encodeURIComponent(name)}`, ManifestSchema);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
};
