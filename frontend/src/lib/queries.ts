import { useEffect, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  ApiError,
  cinemoryApi,
  type Health,
  type LibraryReel,
  type Manifest,
  type Occasion,
  type ReelJobSubmitResponse,
  type ReelRequest,
  type ReelResponse,
  type UploadReelRequest,
} from "./api";

export const queryKeys = {
  health: ["health"] as const,
  occasions: ["occasions"] as const,
  manifest: (name: string) => ["manifest", name] as const,
  myLibrary: ["myLibrary"] as const,
};

export function useHealth(): UseQueryResult<Health> {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => cinemoryApi.health(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useOccasions(): UseQueryResult<Occasion[]> {
  return useQuery({
    queryKey: queryKeys.occasions,
    queryFn: () => cinemoryApi.occasions(),
    staleTime: 5 * 60_000,
  });
}

export function useManifest(name: string | null): UseQueryResult<Manifest | null> {
  return useQuery({
    queryKey: queryKeys.manifest(name ?? ""),
    queryFn: () => cinemoryApi.manifest(name as string),
    enabled: !!name,
    staleTime: Infinity,
  });
}

/** The signed-in tenant's own reel library (GET /me/library). `enabled` is
 *  driven by the caller (MyReels passes `useAuthUser().user !== null`) — this
 *  hook never fetches on its own just because it was rendered, since the
 *  route 401s for anyone who isn't signed in.
 *
 *  `retry: false` overrides the app-wide default (`main.tsx` sets `retry: 1`):
 *  a 401 here means "this deployment doesn't have multitenancy configured, or
 *  I'm signed out" — neither improves by retrying, so MyReels can render its
 *  honest degrade message immediately instead of after a pointless extra
 *  round trip. */
export function useMyLibrary(enabled: boolean): UseQueryResult<LibraryReel[]> {
  return useQuery({
    queryKey: queryKeys.myLibrary,
    queryFn: () => cinemoryApi.myLibrary(),
    enabled,
    retry: false,
  });
}

/** Erase every object under the signed-in tenant's storage prefix
 *  (DELETE /me/data). On success, invalidates the library query so MyReels
 *  refetches and renders the now-empty state. */
export function useDeleteMyData() {
  const qc = useQueryClient();
  return useMutation<{ deleted: number }, Error, void>({
    mutationFn: () => cinemoryApi.deleteMyData(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.myLibrary });
    },
  });
}

/** The reel-generation mutation. On success we prime the manifest cache so the
 *  provenance panel can render instantly from GET /reels/{name}. */
export function useCreateReel() {
  const qc = useQueryClient();
  return useMutation<ReelResponse, Error, ReelRequest>({
    mutationFn: (body) => cinemoryApi.createReel(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.manifest(data.reel_name) });
    },
  });
}

/** Real-photo reel mutation: streams the selected image files to
 *  POST /reels/upload-multipart. Like useCreateReel, it primes the manifest
 *  cache so the provenance panel renders the sealed per-step manifest. Kept
 *  for callers that want a single blocking request; GenerateReel itself uses
 *  the async submit + poll pair below instead, so a multi-minute live render
 *  never blocks one HTTP request past the edge proxy's timeout. */
export function useUploadReel() {
  const qc = useQueryClient();
  return useMutation<ReelResponse, Error, UploadReelRequest>({
    mutationFn: (body) => cinemoryApi.uploadReel(body),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: queryKeys.manifest(data.reel_name) });
    },
  });
}

/** Submit a real-photo reel generation as a background job
 *  (POST /reels/jobs) — the async counterpart to useUploadReel. Resolves
 *  with `{job_id, status: "queued"}` immediately; pair with usePollReelJob
 *  to observe the actual generation outcome. */
export function useSubmitReelJob() {
  return useMutation<ReelJobSubmitResponse, Error, UploadReelRequest>({
    mutationFn: (body) => cinemoryApi.submitReelJob(body),
  });
}

/** How often a submitted job's status is polled. */
export const REEL_JOB_POLL_INTERVAL_MS = 4_000;

/** Bounded total poll duration (~12 min) before the caller gives up and
 *  surfaces the honest "taking longer than expected" state — the same copy
 *  a synchronous gateway timeout already used, reused via a synthetic 504
 *  ApiError below rather than a new UI branch. */
export const REEL_JOB_MAX_POLL_MS = 12 * 60_000;

/** A poll tick that fails before even reaching a real job status (network
 *  blip, transient 5xx) is tolerated this many times IN A ROW before the
 *  poll gives up — a brief hiccup must never abort an in-progress
 *  multi-minute render. Resets on every successful tick. */
export const REEL_JOB_MAX_CONSECUTIVE_ERRORS = 3;

export interface ReelJobPollState {
  /** The sealed reel once the job status is "done". */
  result: ReelResponse | null;
  /** Set once the job status is "failed", the max poll duration elapses, or
   *  the consecutive-error budget is exhausted. Always an Error (usually the
   *  same ApiError getReelJob already throws) so the caller's existing
   *  error-rendering branch — built for the old synchronous mutation — can
   *  be reused unchanged. */
  error: Error | null;
  /** True while a submitted job is still queued/running and being polled. */
  isPolling: boolean;
}

const IDLE_POLL_STATE: ReelJobPollState = { result: null, error: null, isPolling: false };

/**
 * Poll `GET /reels/jobs/{jobId}` on an interval until the job reaches a
 * terminal status, a bounded max duration elapses, or the component unmounts.
 * `jobId === null` means "nothing submitted yet" — idle, no polling.
 *
 * Deliberately a plain interval loop, not `useQuery` + `refetchInterval`:
 * job polling needs a hard wall-clock ceiling (~12 min) and a small
 * consecutive-failure budget shared ACROSS ticks, which is a different shape
 * than react-query's per-fetch retry/backoff. Primes the manifest cache on
 * success exactly like useCreateReel/useUploadReel do. The very first tick
 * fires immediately (no interval wait) — offline/demo generation can finish
 * near-instantly, so a job may already be "done" the first time it's polled.
 */
export function usePollReelJob(jobId: string | null): ReelJobPollState {
  const qc = useQueryClient();
  const [state, setState] = useState<ReelJobPollState>(IDLE_POLL_STATE);

  useEffect(() => {
    if (!jobId) {
      setState(IDLE_POLL_STATE);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof window.setTimeout> | undefined;
    let consecutiveErrors = 0;
    const startedAt = Date.now();
    setState({ result: null, error: null, isPolling: true });

    const giveUp = (error: Error) => {
      if (cancelled) return;
      setState({ result: null, error, isPolling: false });
    };

    // Schedules the next tick, unless the wall-clock ceiling has already
    // passed — in which case this poll honestly gives up as a timeout.
    const scheduleNext = () => {
      if (cancelled) return;
      if (Date.now() - startedAt >= REEL_JOB_MAX_POLL_MS) {
        giveUp(new ApiError("The reel is taking longer than expected to render.", 504));
        return;
      }
      timer = window.setTimeout(tick, REEL_JOB_POLL_INTERVAL_MS);
    };

    async function tick() {
      if (cancelled) return;
      try {
        const status = await cinemoryApi.getReelJob(jobId as string);
        if (cancelled) return;
        consecutiveErrors = 0;
        if (status.status === "done") {
          const result = status.result ?? null;
          if (result) qc.invalidateQueries({ queryKey: queryKeys.manifest(result.reel_name) });
          setState({ result, error: null, isPolling: false });
          return;
        }
        if (status.status === "failed") {
          giveUp(new ApiError(status.error ?? "Generation failed."));
          return;
        }
        scheduleNext();
      } catch (err) {
        if (cancelled) return;
        consecutiveErrors += 1;
        if (consecutiveErrors > REEL_JOB_MAX_CONSECUTIVE_ERRORS) {
          giveUp(err instanceof Error ? err : new Error(String(err)));
          return;
        }
        scheduleNext();
      }
    }

    tick();

    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [jobId, qc]);

  return state;
}
