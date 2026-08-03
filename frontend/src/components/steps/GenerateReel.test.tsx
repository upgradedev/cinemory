import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GenerateReel, newReelName } from "./GenerateReel";
import { useReelStore } from "@/store/useReelStore";
import { REEL_JOB_POLL_INTERVAL_MS } from "@/lib/queries";
import { ApiError, cinemoryApi, type Occasion, type ReelResponse } from "@/lib/api";

const REEL: ReelResponse = {
  reel_name: "cinemory-reel",
  occasion: "anniversary",
  reel_url: "b2://bucket/r.mp4",
  reel_sha256: "a".repeat(64),
  manifest_uri: "b2://bucket/m.json",
  manifest_hash: "b".repeat(64),
  steps: 6,
};

const ANNIVERSARY: Occasion = {
  key: "anniversary",
  label: "Anniversary",
  music_style: "warm strings",
  tempo: 96,
  seconds_per_clip: 3.5,
  transition: "cross-dissolve",
  title_style: "serif",
  aspect_ratio: "16:9",
};

function imageFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
}

function renderGenerate(
  onComplete = vi.fn(),
  props: { resumeJobId?: string | null; onStartNew?: () => void } = {},
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <GenerateReel onComplete={onComplete} {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, onComplete };
}

beforeEach(() => {
  useReelStore.getState().reset();
  // Default: occasions available so the subtitle can name the occasion.
  vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([ANNIVERSARY]);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("<GenerateReel /> — synthetic (no photos) path", () => {
  it("auto-fires the synth reel and completes to the parent on success", async () => {
    useReelStore.getState().setOccasion("anniversary");
    const createSpy = vi.spyOn(cinemoryApi, "createReel").mockResolvedValue(REEL);

    const { onComplete } = renderGenerate();
    expect(screen.getByRole("heading", { name: /rolling/i })).toBeInTheDocument();

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(REEL), {
      timeout: 3000,
    });
    // No photos selected → the synthetic /reels path with a derived shape.
    expect(createSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        // Unique per run, never the old shared constant: sharing one name made
        // GET /reels/{name} resolve a different run's reel, which broke the
        // Provenance panel's re-fetch. See newReelName().
        name: expect.stringMatching(/^cinemory-reel-[a-z0-9]+-[a-z0-9]+$/),
        occasion: "anniversary",
        chapters: 2,
        per_chapter: 1,
      }),
    );
  });

  it("names every reel uniquely so provenance re-fetch resolves the right one", () => {
    const names = new Set(Array.from({ length: 200 }, () => newReelName()));
    expect(names.size).toBe(200);
    for (const n of names) {
      expect(n).toMatch(/^cinemory-reel-[a-z0-9-]+$/);
      // the backend sanitises this into an object key — keep it key-safe
      expect(n).not.toMatch(/[^a-z0-9-]/);
    }
  });
});

describe("<GenerateReel /> — real-photo async job path", () => {
  it("submits a background job, polls it, and completes when the first poll is already done (offline/demo)", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore
      .getState()
      .addPhotos([imageFile("a.png"), imageFile("b.png")]);
    const submitSpy = vi
      .spyOn(cinemoryApi, "submitReelJob")
      .mockResolvedValue({ job_id: "job-1", status: "queued" });
    const getJobSpy = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockResolvedValue({ job_id: "job-1", status: "done", result: REEL });
    // The old sync client functions stay in place but must never be called
    // from this flow.
    const uploadSpy = vi.spyOn(cinemoryApi, "uploadReel");
    const createSpy = vi.spyOn(cinemoryApi, "createReel");

    const { onComplete } = renderGenerate();
    // Plural photo count is shown in the summary line. Matched on the whole
    // line, not a loose /2 photos/, because the estimate above it names the
    // same count and a loose matcher would find both.
    expect(
      screen.getByText((_, el) => el?.textContent === "2 chapters · 2 photos"),
    ).toBeInTheDocument();

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(REEL), {
      timeout: 3000,
    });
    expect(submitSpy).toHaveBeenCalledWith(
      expect.objectContaining({ occasion: "anniversary", chapters: 2 }),
    );
    expect(submitSpy.mock.calls[0]?.[0].files).toHaveLength(2);
    expect(getJobSpy).toHaveBeenCalledWith("job-1");
    expect(uploadSpy).not.toHaveBeenCalled();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("keeps polling across queued → running → done before completing", async () => {
    vi.useFakeTimers();
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    vi.spyOn(cinemoryApi, "submitReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "queued",
    });
    const getJobSpy = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockResolvedValueOnce({ job_id: "job-1", status: "queued" })
      .mockResolvedValueOnce({ job_id: "job-1", status: "running" })
      .mockResolvedValueOnce({ job_id: "job-1", status: "done", result: REEL });

    const { onComplete } = renderGenerate();

    // Flush the submit and the poll's immediate first tick (queued).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("heading", { name: /rolling/i })).toBeInTheDocument();
    expect(getJobSpy).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();

    // Second tick (running) — one interval later.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJobSpy).toHaveBeenCalledTimes(2);
    expect(onComplete).not.toHaveBeenCalled();

    // Third tick (done) — another interval later.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REEL_JOB_POLL_INTERVAL_MS);
    });
    expect(getJobSpy).toHaveBeenCalledTimes(3);

    // The ~650ms completion beat (all stages fill in, then onComplete fires).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(700);
    });
    expect(onComplete).toHaveBeenCalledWith(REEL);
  });

  it("shows the friendly failure copy — never the raw exception class name — as the headline when the job fails", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    vi.spyOn(cinemoryApi, "submitReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "queued",
    });
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "failed",
      error: "RuntimeError",
    });

    renderGenerate();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /didn’t finish/i }),
      ).toBeInTheDocument(),
    );
    // The friendly copy is the headline...
    expect(screen.getByText(/we couldn’t finish this one/i)).toBeInTheDocument();
    // ...the raw exception class name is kept only as the small technical
    // detail underneath, never as the headline itself.
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();
  });

  it("surfaces a submit-level failure (e.g. a bad request) without ever polling", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    vi.spyOn(cinemoryApi, "submitReelJob").mockRejectedValue(
      new ApiError("Request to /reels/jobs failed (400).", 400),
    );
    const getJobSpy = vi.spyOn(cinemoryApi, "getReelJob");

    renderGenerate();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /didn’t finish/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/failed \(400\)/i)).toBeInTheDocument();
    // A submit that never even got a job id has nothing to poll.
    expect(getJobSpy).not.toHaveBeenCalled();
  });

  it("retry re-submits a fresh job", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    const submitSpy = vi
      .spyOn(cinemoryApi, "submitReelJob")
      .mockResolvedValue({ job_id: "job-1", status: "queued" });
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "job-1",
      status: "failed",
      error: "RuntimeError",
    });

    renderGenerate();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /didn’t finish/i }),
      ).toBeInTheDocument(),
    );

    const before = submitSpy.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() =>
      expect(submitSpy.mock.calls.length).toBeGreaterThan(before),
    );
  });
});

describe("<GenerateReel /> — failure handling", () => {
  it("surfaces the error and offers retry + back", async () => {
    useReelStore.getState().setOccasion("anniversary");
    const createSpy = vi
      .spyOn(cinemoryApi, "createReel")
      .mockRejectedValue(new Error("render blew up"));

    renderGenerate();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /didn’t finish/i }),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/render blew up/i)).toBeInTheDocument();

    // Retry re-fires the generation (a second attempt).
    const before = createSpy.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() =>
      expect(createSpy.mock.calls.length).toBeGreaterThan(before),
    );

    // Back returns to the occasion step.
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(useReelStore.getState().step).toBe("occasion");
  });

  it("reads a gateway timeout as an honest 'taking longer than expected', with the raw status kept as a secondary detail", async () => {
    useReelStore.getState().setOccasion("anniversary");
    vi.spyOn(cinemoryApi, "createReel").mockRejectedValue(
      new ApiError("Request to /reels failed (504).", 504),
    );

    renderGenerate();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /didn’t finish/i }),
      ).toBeInTheDocument(),
    );

    // The headline is the honest, reassuring copy. Never the raw error.
    expect(
      screen.getByText(/taking longer than expected/i),
    ).toBeInTheDocument();
    // The raw technical detail (path + status) stays available, just not
    // as the headline.
    expect(screen.getByText(/failed \(504\)/i)).toBeInTheDocument();
  });
});

describe("<GenerateReel /> — in-flight render", () => {
  it("shows the staged pipeline with a single photo (singular label)", () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    // A submit that never settles keeps the component in its pending render
    // (jobId never gets set, so it never starts polling either).
    vi.spyOn(cinemoryApi, "submitReelJob").mockReturnValue(new Promise(() => {}));

    renderGenerate();

    expect(screen.getByRole("heading", { name: /rolling/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "2 chapters · 1 photo"),
    ).toBeInTheDocument();
    // The wait is estimated from the photo count, never a fixed phrase.
    expect(
      screen.getByText(/1 photo usually takes about 6 minutes/i),
    ).toBeInTheDocument();
    // The full seven-stage pipeline is listed.
    expect(screen.getByText(/reading your photos/i)).toBeInTheDocument();
    expect(
      screen.getByText(/sealing cryptographic provenance/i),
    ).toBeInTheDocument();
  });
});

describe("<GenerateReel /> — resuming a reel from its link", () => {
  it("polls the reel the link names and submits NOTHING", async () => {
    // The whole point: the tab that submitted this is gone. There are no
    // photos and no occasion left in memory, only the link.
    const submitSpy = vi.spyOn(cinemoryApi, "submitReelJob");
    const createSpy = vi.spyOn(cinemoryApi, "createReel");
    const getJobSpy = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockResolvedValue({ job_id: "abcdefgh12", status: "done", result: REEL });

    const { onComplete } = renderGenerate(vi.fn(), { resumeJobId: "abcdefgh12" });

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(REEL), {
      timeout: 3000,
    });
    expect(getJobSpy).toHaveBeenCalledWith("abcdefgh12");
    // No photos in this tab must NOT fall through to the synthetic path.
    expect(submitSpy).not.toHaveBeenCalled();
    expect(createSpy).not.toHaveBeenCalled();
  });

  it("says it is picking the reel back up, and does not claim 0 photos", () => {
    vi.spyOn(cinemoryApi, "getReelJob").mockReturnValue(new Promise(() => {}));

    renderGenerate(vi.fn(), { resumeJobId: "abcdefgh12" });

    expect(screen.getByRole("heading", { name: /rolling/i })).toBeInTheDocument();
    expect(screen.getByText(/picking this reel back up/i)).toBeInTheDocument();
    expect(screen.getByText(/already in progress/i)).toBeInTheDocument();
    expect(screen.queryByText(/0 photos/i)).not.toBeInTheDocument();
  });

  it("says plainly when the link leads to no reel, instead of spinning", async () => {
    // An unknown or expired id answers 404. That is a final answer, so it must
    // land at once rather than burning the transient-error budget first.
    vi.spyOn(cinemoryApi, "getReelJob").mockRejectedValue(
      new ApiError("Request to /reels/jobs/gone failed (404).", 404),
    );
    const onStartNew = vi.fn();

    renderGenerate(vi.fn(), { resumeJobId: "abcdefgh12", onStartNew });

    expect(
      await screen.findByRole("heading", { name: /couldn.t find that reel/i }),
    ).toBeInTheDocument();
    const startNew = screen.getByRole("button", { name: /start a new reel/i });
    await userEvent.click(startNew);
    expect(onStartNew).toHaveBeenCalled();
  });

  it("offers only a fresh start when a resumed reel fails for another reason", async () => {
    // Retry and Back both lead somewhere empty after a refresh: there are no
    // photos to resubmit and no occasion to go back to.
    vi.spyOn(cinemoryApi, "getReelJob").mockResolvedValue({
      job_id: "abcdefgh12",
      status: "failed",
      error: "RuntimeError",
    });
    const onStartNew = vi.fn();

    renderGenerate(vi.fn(), { resumeJobId: "abcdefgh12", onStartNew });

    expect(
      await screen.findByRole("heading", { name: /didn.t finish/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^retry$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^back$/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /start a new reel/i }));
    expect(onStartNew).toHaveBeenCalled();
  });
});

describe("<GenerateReel /> — the link that makes a refresh safe", () => {
  it("puts the reel in the address bar as soon as it is submitted, not when it finishes", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    vi.spyOn(cinemoryApi, "submitReelJob").mockResolvedValue({
      job_id: "abcdefgh12",
      status: "queued",
    });
    // Never settles: the reel is still being made, which is exactly when
    // someone refreshes and used to lose it.
    vi.spyOn(cinemoryApi, "getReelJob").mockReturnValue(new Promise(() => {}));

    renderGenerate();

    await waitFor(() => expect(window.location.hash).toBe("#reel/abcdefgh12"));
  });
});
