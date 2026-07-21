import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ReelResult } from "./ReelResult";
import type { ReelResponse } from "@/lib/api";

/** A live, non-degraded reel response (the backend always sends these fields). */
const liveReel: ReelResponse = {
  reel_name: "demo-reel",
  occasion: "anniversary",
  reel_url: "https://cinemory.s3.example/demo-reel/reels/ab/cd/reel.mp4",
  playback_url: "/reels/demo-reel/video",
  reel_sha256: "a".repeat(64),
  manifest_uri: "https://cinemory.s3.example/demo-reel/manifests/ab/cd/manifest.json",
  manifest_hash: "b".repeat(64),
  steps: 4,
  provider: "genblaze",
  provider_degraded: false,
};

const degradedReel: ReelResponse = {
  ...liveReel,
  provider: "fake-genblaze",
  provider_degraded: true,
  degrade_reason: "RuntimeError",
};

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  // The component's data hooks (occasions/manifest) fire fetches; a quiet 404
  // keeps them in a harmless empty state without network access.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "not found" }),
    } as Response),
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("<ReelResult /> — honest degrade surfacing", () => {
  it("shows the offline-generator badge and plain-English note when degraded", () => {
    renderWithQuery(<ReelResult reel={degradedReel} />);
    expect(
      screen.getByText(/rendered on the built-in offline generator/i),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        /live ai generation was unavailable for this run; storage and provenance are real/i,
      ).length,
    ).toBeGreaterThan(0);
  });

  it("shows no degrade badge on a live, non-degraded reel", () => {
    renderWithQuery(<ReelResult reel={liveReel} />);
    expect(
      screen.queryByText(/rendered on the built-in offline generator/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/live ai generation was unavailable/i),
    ).not.toBeInTheDocument();
  });
});

describe("<ReelResult /> — playback source", () => {
  it("plays a live reel through the stable api playback route", () => {
    const { container } = renderWithQuery(<ReelResult reel={liveReel} />);
    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.getAttribute("src")).toBe("/reels/demo-reel/video");
  });

  it("shows the poster (not a broken player) for a degraded run", () => {
    const { container } = renderWithQuery(<ReelResult reel={degradedReel} />);
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText(/the preview plays when the reel comes from live ai/i))
      .toBeInTheDocument();
  });
});
