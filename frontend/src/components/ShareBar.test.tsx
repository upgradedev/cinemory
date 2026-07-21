import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ShareBar } from "./ShareBar";
import type { ReelResponse } from "@/lib/api";

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

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  writeText.mockClear();
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  // @ts-expect-error test cleanup of the shimmed clipboard
  delete navigator.clipboard;
});

describe("<ShareBar /> — honest share affordances", () => {
  it("drops the dead Instagram/YouTube homepage links", () => {
    render(<ShareBar reel={liveReel} />);
    expect(screen.queryByRole("link", { name: /instagram/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /youtube/i })).not.toBeInTheDocument();
    // The real share-by-url platforms stay, pointing at their sharer endpoints.
    expect(screen.getByRole("link", { name: /facebook/i })).toHaveAttribute(
      "href",
      expect.stringContaining("facebook.com/sharer"),
    );
    expect(screen.getByRole("link", { name: /linkedin/i })).toHaveAttribute(
      "href",
      expect.stringContaining("share-offsite"),
    );
  });

  it("copies the app share URL with checkmark feedback", async () => {
    render(<ShareBar reel={liveReel} />);
    await userEvent.click(screen.getByRole("button", { name: /copy link/i }));

    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(await screen.findByText("Copied")).toBeInTheDocument();
    expect(screen.getByText(/link copied to clipboard/i)).toBeInTheDocument();
  });

  it("surfaces a copy failure honestly instead of fake success", async () => {
    writeText.mockRejectedValueOnce(new Error("denied"));
    render(<ShareBar reel={liveReel} />);
    await userEvent.click(screen.getByRole("button", { name: /copy link/i }));

    expect(await screen.findByText(/copy failed/i)).toBeInTheDocument();
    expect(screen.queryByText("Copied")).not.toBeInTheDocument();
  });
});
