import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import {
  REEL_JOB_MAX_CONSECUTIVE_ERRORS,
  REEL_JOB_MAX_POLL_MS,
  REEL_JOB_POLL_INTERVAL_MS,
  useCreateReel,
  useHealth,
  useManifest,
  useOccasions,
  usePollReelJob,
  useSubmitReelJob,
  useUploadReel,
} from "./queries";
import { ApiError, cinemoryApi, type Occasion, type ReelResponse } from "./api";

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

const OCCASION: Occasion = {
  key: "wedding",
  label: "Wedding",
  music_style: "dreamy",
  tempo: 90,
  seconds_per_clip: 3,
  transition: "cross-dissolve",
  title_style: "serif",
  aspect_ratio: "16:9",
};

const REEL: ReelResponse = {
  reel_name: "demo",
  occasion: "wedding",
  reel_url: "b2://bucket/demo.mp4",
  reel_sha256: "a".repeat(64),
  manifest_uri: "b2://bucket/m.json",
  manifest_hash: "b".repeat(64),
  steps: 4,
};

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useHealth / useOccasions", () => {
  it("useHealth surfaces the backend mode", async () => {
    vi.spyOn(cinemoryApi, "health").mockResolvedValue({
      status: "ok",
      service: "cinemory",
      mode: "offline",
    });
    const { result } = renderHook(() => useHealth(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.mode).toBe("offline");
  });

  it("useOccasions returns the presets", async () => {
    vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([OCCASION]);
    const { result } = renderHook(() => useOccasions(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([OCCASION]);
  });
});

describe("useManifest", () => {
  it("stays disabled (never fetches) when name is null", () => {
    const spy = vi.spyOn(cinemoryApi, "manifest");
    const { result } = renderHook(() => useManifest(null), {
      wrapper: wrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(spy).not.toHaveBeenCalled();
  });

  it("fetches the manifest once a name is supplied", async () => {
    const manifest = { reel_name: "demo", steps: [] } as never;
    vi.spyOn(cinemoryApi, "manifest").mockResolvedValue(manifest);
    const { result } = renderHook(() => useManifest("demo"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(cinemoryApi.manifest).toHaveBeenCalledWith("demo");
  });
});

describe("reel mutations prime the manifest cache", () => {
  it("useCreateReel resolves the created reel", async () => {
    vi.spyOn(cinemoryApi, "createReel").mockResolvedValue(REEL);
    const { result } = renderHook(() => useCreateReel(), { wrapper: wrapper() });
    result.current.mutate({
      name: "demo",
      occasion: "wedding",
      chapters: 2,
      per_chapter: 2,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(REEL);
  });

  it("useUploadReel resolves the uploaded reel", async () => {
    vi.spyOn(cinemoryApi, "uploadReel").mockResolvedValue(REEL);
    const { result } = renderHook(() => useUploadReel(), { wrapper: wrapper() });
    result.current.mutate({
      name: "demo",
      occasion: "wedding",
      chapters: 2,
      files: [new File([new Uint8Array([1])], "a.png", { type: "image/png" })],
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(REEL);
  });

  it("useSubmitReelJob resolves the submitted job id (202 + job_id)", async () => {
    vi.spyOn(cinemoryApi, "submitReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "queued",
    });
    const { result } = renderHook(() => useSubmitReelJob(), { wrapper: wrapper() });
    result.current.mutate({
      name: "demo",
      occasion: "wedding",
      chapters: 2,
      files: [new File([new Uint8Array([1])], "a.png", { type: "image/png" })],
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ job_id: "job-1", status: "queued" });
  });
});

describe("usePollReelJob", () => {
  it("stays idle and never polls when jobId is null", () => {
    const spy = vi.spyOn(cinemoryApi, "getReelJob");
    const { result } = renderHook(() => usePollReelJob(null), { wrapper: wrapper() });
    expect(result.current).toEqual({ result: null, error: null, isPolling: false });
    expect(spy).not.toHaveBeenCalled();
  });

  it("resolves on the very first poll when the job is already done — the offline/demo case, where generation can finish before the first check", async () => {
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "done",
      result: REEL,
    });
    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.result).toEqual(REEL));
    expect(result.current.isPolling).toBe(false);
    expect(cinemoryApi.getReelJob).toHaveBeenCalledTimes(1);
  });

  it("surfaces a failed job as an Error carrying the exception class name, never prose, and stops polling", async () => {
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "failed",
      error: "RuntimeError",
    });
    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("RuntimeError");
    expect(result.current.result).toBeNull();
    expect(result.current.isPolling).toBe(false);
  });

  it("falls back to a generic message when a failed job omits the error field", async () => {
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "failed",
    });
    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("Generation failed.");
  });

  it("polls again while queued/running, then resolves once done", async () => {
    vi.useFakeTimers();
    const getJob = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockResolvedValueOnce({ job_id: "job-1", status: "queued" })
      .mockResolvedValueOnce({ job_id: "job-1", status: "running" })
      .mockResolvedValueOnce({ job_id: "job-1", status: "done", result: REEL });

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });

    // The first tick fires immediately, with no interval wait.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(result.current.isPolling).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJob).toHaveBeenCalledTimes(3);
    expect(result.current.result).toEqual(REEL);
    expect(result.current.isPolling).toBe(false);
  });

  it("tolerates a couple of transient poll errors and recovers once the job answers again", async () => {
    vi.useFakeTimers();
    const getJob = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockRejectedValueOnce(new ApiError("network blip"))
      .mockRejectedValueOnce(new ApiError("network blip"))
      .mockResolvedValueOnce({ job_id: "job-1", status: "done", result: REEL });

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeNull();
    expect(result.current.isPolling).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJob).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBeNull(); // still tolerating, not given up

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJob).toHaveBeenCalledTimes(3);
    expect(result.current.result).toEqual(REEL);
  });

  it("gives up after exhausting the consecutive poll-error budget, and stops scheduling further ticks", async () => {
    vi.useFakeTimers();
    const getJob = vi.spyOn(cinemoryApi, "getReelJob").mockRejectedValue(new ApiError("down"));

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);

    for (let i = 0; i < REEL_JOB_MAX_CONSECUTIVE_ERRORS; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
      });
    }
    expect(getJob).toHaveBeenCalledTimes(REEL_JOB_MAX_CONSECUTIVE_ERRORS + 1);
    expect(result.current.error).not.toBeNull();
    expect(result.current.isPolling).toBe(false);

    // No further ticks scheduled once the poll has given up.
    const callsAtGiveUp = getJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS * 3);
    });
    expect(getJob).toHaveBeenCalledTimes(callsAtGiveUp);
  });

  it("wraps a non-Error rejection (e.g. a thrown string) into an Error when it gives up", async () => {
    vi.useFakeTimers();
    // getReelJob is typed to return a Promise, but a poll must still survive
    // a queryFn that rejects with a non-Error value (a thrown string, say).
    const getJob = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockImplementation(() => Promise.reject("boom"));

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    for (let i = 0; i < REEL_JOB_MAX_CONSECUTIVE_ERRORS; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
      });
    }
    expect(getJob).toHaveBeenCalledTimes(REEL_JOB_MAX_CONSECUTIVE_ERRORS + 1);
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.error?.message).toBe("boom");
    expect(result.current.isPolling).toBe(false);
  });

  it("treats a 404 as a final answer, not a hiccup to retry", async () => {
    // An unknown or expired reel id 404s. Spending the whole transient-error
    // budget on it would make someone who opened a stale link wait ~16 more
    // seconds to be told the same thing.
    vi.useFakeTimers();
    const getJob = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockRejectedValue(new ApiError("Request to /reels/jobs/x failed (404).", 404));

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(getJob).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(false);
    expect((result.current.error as ApiError).status).toBe(404);

    // And it stays stopped: no further ticks are scheduled.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS * 5);
    });
    expect(getJob).toHaveBeenCalledTimes(1);
  });

  it("times out after the bounded max poll duration with the honest 504 ApiError", async () => {
    vi.useFakeTimers();
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "running",
    });

    const { result } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.isPolling).toBe(true);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_MAX_POLL_MS + REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(result.current.isPolling).toBe(false);
    expect(result.current.error).toBeInstanceOf(ApiError);
    // status 504 so the component's existing timeout-copy branch picks it up.
    expect((result.current.error as ApiError).status).toBe(504);
  });

  it("stops polling and updates no state after unmount", async () => {
    vi.useFakeTimers();
    const getJob = vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "running",
    });
    const { unmount } = renderHook(() => usePollReelJob("job-1"), { wrapper: wrapper() });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(getJob).toHaveBeenCalledTimes(1);

    unmount();
    const callsAtUnmount = getJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS * 3);
    });
    expect(getJob).toHaveBeenCalledTimes(callsAtUnmount);
  });
});
