import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShareBar } from "./ShareBar";
import type { ReelResponse } from "@/lib/api";
import { downloadReel, fetchReelFile, shareReel } from "@/lib/share";

// Keep the pure helpers (platformDeepLinks/reelFilename/copyText) real, but
// stub the three side-effecting ones so Share/Download are deterministic.
vi.mock("@/lib/share", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/share")>();
  return {
    ...actual,
    fetchReelFile: vi.fn(),
    shareReel: vi.fn(),
    downloadReel: vi.fn(),
  };
});

const liveReel: ReelResponse = {
  reel_name: "demo-reel",
  occasion: "anniversary",
  reel_url: "https://cinemory.s3.example/demo-reel/reels/ab/cd/reel.mp4",
  playback_url: "/reels/demo-reel/video",
  reel_sha256: "a".repeat(64),
  manifest_uri: null,
  manifest_hash: "b".repeat(64),
  steps: 4,
  provider: "genblaze",
  provider_degraded: false,
};

const mp4 = new File([new Uint8Array([1])], "demo-reel.mp4", {
  type: "video/mp4",
});

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe("<ShareBar /> — Share", () => {
  it("fetches the playback file and reports a successful native share", async () => {
    vi.mocked(fetchReelFile).mockResolvedValue(mp4);
    vi.mocked(shareReel).mockResolvedValue("shared");
    render(<ShareBar reel={liveReel} />);

    await userEvent.click(screen.getByRole("button", { name: /^share$/i }));
    expect(fetchReelFile).toHaveBeenCalledWith(
      "/reels/demo-reel/video",
      "demo-reel.mp4",
    );
    expect(await screen.findByText(/share shared\./i)).toBeInTheDocument();
  });

  it("guides the user when native share is unsupported", async () => {
    vi.mocked(fetchReelFile).mockResolvedValue(mp4);
    vi.mocked(shareReel).mockResolvedValue("unsupported");
    render(<ShareBar reel={liveReel} />);

    await userEvent.click(screen.getByRole("button", { name: /^share$/i }));
    expect(
      await screen.findByText(/native share isn’t available here/i),
    ).toBeInTheDocument();
  });

  it("surfaces a share failure honestly", async () => {
    vi.mocked(fetchReelFile).mockRejectedValue(new Error("net"));
    render(<ShareBar reel={liveReel} />);

    await userEvent.click(screen.getByRole("button", { name: /^share$/i }));
    expect(await screen.findByText(/share failed:/i)).toBeInTheDocument();
  });
});

describe("<ShareBar /> — Download", () => {
  it("downloads the fetched file", async () => {
    vi.mocked(fetchReelFile).mockResolvedValue(mp4);
    render(<ShareBar reel={liveReel} />);

    await userEvent.click(screen.getByRole("button", { name: /download/i }));
    expect(fetchReelFile).toHaveBeenCalled();
    expect(downloadReel).toHaveBeenCalledWith(mp4, "demo-reel.mp4");
  });

  it("surfaces a download failure honestly", async () => {
    vi.mocked(fetchReelFile).mockRejectedValue(new Error("boom"));
    render(<ShareBar reel={liveReel} />);

    await userEvent.click(screen.getByRole("button", { name: /download/i }));
    expect(await screen.findByText(/download failed:/i)).toBeInTheDocument();
  });
});

describe("<ShareBar /> — offline reel", () => {
  it("disables Share/Download and explains why for a degraded run", () => {
    const offline: ReelResponse = {
      ...liveReel,
      playback_url: null,
      provider: "fake-genblaze",
      provider_degraded: true,
    };
    render(<ShareBar reel={offline} />);

    expect(screen.getByRole("button", { name: /^share$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /download/i })).toBeDisabled();
    expect(
      screen.getByText(/no\s+playable video to share yet/i),
    ).toBeInTheDocument();
  });
});
