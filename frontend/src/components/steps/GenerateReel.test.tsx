import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GenerateReel } from "./GenerateReel";
import { useReelStore } from "@/store/useReelStore";
import { cinemoryApi, type Occasion, type ReelResponse } from "@/lib/api";

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

function renderGenerate(onComplete = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const utils = render(
    <QueryClientProvider client={qc}>
      <GenerateReel onComplete={onComplete} />
    </QueryClientProvider>,
  );
  return { ...utils, onComplete };
}

beforeEach(() => {
  useReelStore.getState().reset();
  // Default: occasions available so the subtitle can name the occasion.
  vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([ANNIVERSARY]);
});

afterEach(() => vi.restoreAllMocks());

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
        name: "cinemory-reel",
        occasion: "anniversary",
        chapters: 2,
        per_chapter: 1,
      }),
    );
  });
});

describe("<GenerateReel /> — real-photo upload path", () => {
  it("streams the selected files and completes on success", async () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore
      .getState()
      .addPhotos([imageFile("a.png"), imageFile("b.png"), imageFile("c.png")]);
    const uploadSpy = vi
      .spyOn(cinemoryApi, "uploadReel")
      .mockResolvedValue(REEL);
    const createSpy = vi.spyOn(cinemoryApi, "createReel");

    const { onComplete } = renderGenerate();
    // Plural photo count is shown in the summary line.
    expect(screen.getByText(/3 photos/i)).toBeInTheDocument();

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(REEL), {
      timeout: 3000,
    });
    expect(uploadSpy).toHaveBeenCalledWith(
      expect.objectContaining({ occasion: "anniversary", chapters: 2 }),
    );
    expect(uploadSpy.mock.calls[0]?.[0].files).toHaveLength(3);
    // The synthetic path is never touched when real photos exist.
    expect(createSpy).not.toHaveBeenCalled();
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
});

describe("<GenerateReel /> — in-flight render", () => {
  it("shows the staged pipeline with a single photo (singular label)", () => {
    useReelStore.getState().setOccasion("anniversary");
    useReelStore.getState().addPhotos([imageFile("only.png")]);
    // A request that never settles keeps the component in its pending render.
    vi.spyOn(cinemoryApi, "uploadReel").mockReturnValue(new Promise(() => {}));

    renderGenerate();

    expect(screen.getByRole("heading", { name: /rolling/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByText(/1 photo(?!s)/i)).toBeInTheDocument();
    // The full seven-stage pipeline is listed.
    expect(screen.getByText(/reading your photos/i)).toBeInTheDocument();
    expect(
      screen.getByText(/sealing cryptographic provenance/i),
    ).toBeInTheDocument();
  });
});
