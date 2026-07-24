import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ReelResult } from "./ReelResult";
import { useReelStore, type LocalPhoto } from "@/store/useReelStore";
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

describe("<ReelResult /> — Ken Burns slideshow fallback", () => {
  const storePhotos: LocalPhoto[] = [1, 2, 3].map((i) => ({
    id: `p${i}`,
    file: new File([`f${i}`], `photo-${i}.png`, { type: "image/png" }),
    url: `blob:mock-${i}`,
    name: `photo-${i}.png`,
    alt: `photo-${i}.png`,
  }));

  beforeEach(() => useReelStore.setState({ photos: storePhotos }));
  afterEach(() => useReelStore.setState({ photos: [] }));

  it("plays a slideshow of the user's photos when there is no playable video", () => {
    const { container } = renderWithQuery(<ReelResult reel={degradedReel} />);
    expect(container.querySelector("video")).toBeNull();

    const slideshow = screen.getByTestId("kenburns-slideshow");
    expect(slideshow).toHaveAttribute("role", "img");
    expect(slideshow).toHaveAccessibleName(/slideshow of your 3 uploaded photos/i);
    expect(slideshow.querySelectorAll("img")).toHaveLength(3);
    // The money screen is alive — the static poster copy is gone…
    expect(
      screen.queryByText(/the preview plays when the reel comes from live ai/i),
    ).not.toBeInTheDocument();
    // …and the honest degrade chip overlays the letterbox.
    expect(
      screen.getByText(/rendered on the built-in offline generator/i),
    ).toBeInTheDocument();
  });

  it("never shows the slideshow when a real video plays", () => {
    const { container } = renderWithQuery(<ReelResult reel={liveReel} />);
    expect(container.querySelector("video")).not.toBeNull();
    expect(screen.queryByTestId("kenburns-slideshow")).not.toBeInTheDocument();
  });

  it("keeps the letterbox width-driven so narrow viewports can't overflow", () => {
    const { container } = renderWithQuery(<ReelResult reel={liveReel} />);
    const letterbox = container.querySelector(".letterbox") as HTMLElement;
    // Width-driven aspect box + absolutely-filled media: the height can never
    // go stale on a desktop→mobile resize.
    expect(letterbox.className).toContain("aspect-video");
    expect(letterbox.className).toContain("w-full");
    expect(letterbox.querySelector("video")?.className).toContain("absolute");
    // Both grid columns may shrink below content size (min-w-0) — without it
    // the letterbox column pins a ~761px min-content width at 375w.
    const columns = container.querySelectorAll(".lg\\:col-span-3, .lg\\:col-span-2");
    expect(columns.length).toBe(2);
    columns.forEach((c) => expect((c as HTMLElement).className).toContain("min-w-0"));
  });
});
