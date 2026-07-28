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
import { getIdToken } from "./auth";

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

// Real-photo upload: the user's selected image files are streamed to
// `POST /reels/upload-multipart` (multipart/form-data — raw bytes, no base64
// inflation). The response is the same sealed ReelResponse as the synthetic
// path, so the reel + provenance render code is shared.
export interface UploadReelRequest {
  name: string;
  occasion: string;
  chapters: number;
  bridges?: boolean;
  files: File[];
}

export const ReelResponseSchema = z.object({
  reel_name: z.string(),
  occasion: z.string().optional(),
  // Canonical storage URL (provenance display) — the bucket is private, so this
  // is NOT directly fetchable. Playback/download go through `playback_url`.
  reel_url: z.string().nullable(),
  // Stable api-relative playback route (`/reels/{name}/video`): the backend
  // 302s to a fresh presigned URL in live mode, or streams bytes offline.
  // Optional so responses from older backends still parse.
  playback_url: z.string().nullable().optional(),
  reel_sha256: z.string(),
  manifest_uri: z.string().nullable(),
  manifest_hash: z.string(),
  steps: z.number().int(),
  // Honest generation provenance: which provider actually generated, and
  // whether this run degraded to the built-in offline generator mid-request.
  provider: z.string().optional(),
  provider_degraded: z.boolean().optional(),
  degrade_reason: z.string().optional(),
});
export type ReelResponse = z.infer<typeof ReelResponseSchema>;

// Async submit + poll (POST /reels/jobs / GET /reels/jobs/{job_id}) — the
// non-blocking counterpart to POST /reels/upload for a multi-minute live
// render (see cinemory.jobs on the backend). A job's terminal `result` is the
// IDENTICAL shape as ReelResponse above, so the success/render path is shared
// with the synchronous flow unchanged.
export const ReelJobSubmitResponseSchema = z.object({
  job_id: z.string(),
  status: z.string(),
});
export type ReelJobSubmitResponse = z.infer<typeof ReelJobSubmitResponseSchema>;

export const ReelJobStatusSchema = z.object({
  job_id: z.string(),
  status: z.enum(["queued", "running", "done", "failed"]),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  result: ReelResponseSchema.optional(),
  // Exception CLASS NAME only when status is "failed" (see cinemory.jobs) —
  // never prose, never a stack trace. The UI keeps this out of the headline.
  error: z.string().optional(),
});
export type ReelJobStatus = z.infer<typeof ReelJobStatusSchema>;

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

// Optional per-user multitenancy (GET /me/library, DELETE /me/data — see
// cinemory.api and lib/auth.ts). Both routes 401 for a guest caller; the UI
// only ever calls them when signed in (see MyReels.tsx).
export const LibraryReelSchema = z.object({
  reel_name: z.string(),
  manifest_hash: z.string().nullable(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
});
export type LibraryReel = z.infer<typeof LibraryReelSchema>;

const MyLibraryResponseSchema = z.object({ reels: z.array(LibraryReelSchema) });

const DeleteMyDataResponseSchema = z.object({ deleted: z.number().int() });

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
    throw new ApiError("Network unreachable. Check your connection and try again.", undefined, err);
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

/** Read a File's bytes and resolve the RAW base64 payload — no leading
 *  `data:<mime>;base64,` prefix. This is the shape the JSON job/upload routes
 *  decode server-side via Python's `base64.b64decode` (see cinemory.api). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error(`Failed to read ${file.name} as base64.`));
        return;
      }
      const comma = result.indexOf(",");
      resolve(comma === -1 ? result : result.slice(comma + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error(`Failed to read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

/** Merges a fresh `Authorization: Bearer <id token>` into `headers` when a
 *  user is signed in (see lib/auth.ts::getIdToken). Signed out, or auth
 *  disabled on this build — the overwhelmingly common case, and the ONLY
 *  case any test before this feature existed ever exercised — returns
 *  `headers` completely UNCHANGED (same reference when a base was given, or
 *  `undefined` when it wasn't), so every reel call below is byte-identical
 *  to its pre-multitenancy fetch for a guest. Never caches the token: a
 *  fresh one is requested on every single call.
 *
 *  The `| undefined` overload matters, not just the empty-object case: the
 *  shared `request()` helper spreads `...init` AFTER its own default
 *  `headers`, so an explicit-but-empty `init.headers` key would still
 *  clobber the default `Accept` header that a guest call relies on. Callers
 *  with no base headers (uploadReel/getReelJob/manifest) must therefore omit
 *  the `headers` key entirely when there's no token — see their `auth ? {...}
 *  : undefined` pattern below — not pass an empty object. */
async function withAuth(
  headers?: Record<string, string>,
): Promise<Record<string, string> | undefined> {
  const token = await getIdToken();
  if (!token) return headers;
  return { ...(headers ?? {}), Authorization: `Bearer ${token}` };
}

export const cinemoryApi = {
  health(): Promise<Health> {
    return request("/health", HealthSchema);
  },

  async occasions(): Promise<Occasion[]> {
    const { occasions } = await request("/occasions", OccasionsResponseSchema);
    return occasions;
  },

  async createReel(body: ReelRequest): Promise<ReelResponse> {
    return request("/reels", ReelResponseSchema, {
      method: "POST",
      headers: await withAuth({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
  },

  /** Generate a reel from real photo bytes via multipart/form-data. We do NOT
   *  set Content-Type — the browser adds the multipart boundary itself. */
  async uploadReel({ name, occasion, chapters, bridges = false, files }: UploadReelRequest): Promise<ReelResponse> {
    const form = new FormData();
    form.append("name", name);
    form.append("occasion", occasion);
    form.append("chapters", String(chapters));
    form.append("bridges", String(bridges));
    for (const file of files) form.append("files", file, file.name);
    const auth = await withAuth();
    return request("/reels/upload-multipart", ReelResponseSchema, {
      method: "POST",
      body: form,
      ...(auth ? { headers: auth } : {}),
    });
  },

  /** Submit a reel generation as a background job (202 + job_id) instead of
   *  blocking for the full render — the async counterpart to `uploadReel`,
   *  for a caller that cannot hold one request open for a multi-minute live
   *  render. Same conceptual payload (name/occasion/chapters/bridges/files),
   *  but the backend's job-submit route only accepts the base64 JSON shape
   *  (identical body to `POST /reels/upload`), not multipart — so files are
   *  base64-encoded here rather than streamed as FormData. Poll the result
   *  with `getReelJob`. */
  async submitReelJob({
    name,
    occasion,
    chapters,
    bridges = false,
    files,
  }: UploadReelRequest): Promise<ReelJobSubmitResponse> {
    const photos = await Promise.all(
      files.map(async (file) => ({
        filename: file.name,
        content_base64: await fileToBase64(file),
      })),
    );
    return request("/reels/jobs", ReelJobSubmitResponseSchema, {
      method: "POST",
      headers: await withAuth({ "Content-Type": "application/json" }),
      body: JSON.stringify({ name, occasion, chapters, bridges, photos }),
    });
  },

  /** Poll a submitted job's status (queued/running/done/failed). A 404
   *  (unknown job id) surfaces as an ApiError like any other failed request —
   *  the caller's poll loop tolerates that the same as a transient failure. */
  async getReelJob(jobId: string): Promise<ReelJobStatus> {
    const auth = await withAuth();
    return request(
      `/reels/jobs/${encodeURIComponent(jobId)}`,
      ReelJobStatusSchema,
      auth ? { headers: auth } : undefined,
    );
  },

  /** Fetch the full sealed manifest. Returns null when the store is not
   *  indexed (the live B2 path returns 404 by design). */
  async manifest(name: string): Promise<Manifest | null> {
    try {
      const auth = await withAuth();
      return await request(
        `/reels/${encodeURIComponent(name)}`,
        ManifestSchema,
        auth ? { headers: auth } : undefined,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },

  /** The signed-in tenant's own reels (GET /me/library). Always attaches the
   *  Authorization header — this route only makes sense for a signed-in
   *  caller (401 for guest) and MyReels never calls it otherwise, but a
   *  missing/expired token still surfaces as an honest ApiError(401) rather
   *  than silently resolving as guest. */
  async myLibrary(): Promise<LibraryReel[]> {
    const auth = await withAuth();
    const { reels } = await request(
      "/me/library",
      MyLibraryResponseSchema,
      auth ? { headers: auth } : undefined,
    );
    return reels;
  },

  /** Erase every object under the signed-in tenant's own storage prefix
   *  (DELETE /me/data). Returns the number of objects deleted. */
  async deleteMyData(): Promise<{ deleted: number }> {
    const auth = await withAuth();
    return request("/me/data", DeleteMyDataResponseSchema, {
      method: "DELETE",
      ...(auth ? { headers: auth } : {}),
    });
  },
};
