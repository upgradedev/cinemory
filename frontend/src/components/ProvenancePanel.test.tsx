import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ProvenancePanel } from "./ProvenancePanel";
import type { ReelResponse } from "@/lib/api";
import goldenRaw from "../test/fixtures/golden-manifest.json?raw";
import goldenExpected from "../test/fixtures/golden-manifest.expected.json";

const goldenManifest = JSON.parse(goldenRaw) as { reel_name: string };

const reel: ReelResponse = {
  reel_name: goldenManifest.reel_name,
  occasion: "wedding",
  reel_url: "b2://cinemory-reels/reel.mp4",
  playback_url: "/reels/x/video",
  reel_sha256: "a".repeat(64),
  manifest_uri: "b2://cinemory-reels/manifest.json",
  manifest_hash: goldenExpected.manifest_hash,
  steps: 4,
  provider: "fake-genblaze",
  provider_degraded: false,
};

function renderWithQuery(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function stubManifestFetch(body: string, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      text: async () => body,
      json: async () => JSON.parse(body),
    } as Response),
  );
}

beforeEach(() => stubManifestFetch(goldenRaw));
afterEach(() => vi.unstubAllGlobals());

describe("<ProvenancePanel /> — in-browser provenance verification", () => {
  it("starts Sealed, then flips to Verified ✓ after a genuine verify", async () => {
    renderWithQuery(<ProvenancePanel reel={reel} />);
    expect(screen.getByText("Sealed")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: /verify provenance/i }),
    );

    expect(await screen.findByText(/verified ✓/i)).toBeInTheDocument();
    expect(screen.queryByText("Sealed")).not.toBeInTheDocument();
    expect(
      screen.getByText(/recomputed the canonical sha-256 in your browser/i),
    ).toBeInTheDocument();
    // The affordance stays available for a re-run.
    expect(
      screen.getByRole("button", { name: /re-verify provenance/i }),
    ).toBeInTheDocument();
  });

  it("shows the red failure state when the manifest bytes don't hash to the seal", async () => {
    stubManifestFetch(
      goldenRaw.replace('"occasion":"wedding"', '"occasion":"Wedding"'),
    );
    renderWithQuery(<ProvenancePanel reel={reel} />);

    await userEvent.click(
      screen.getByRole("button", { name: /verify provenance/i }),
    );

    expect(await screen.findByText(/verification failed/i)).toBeInTheDocument();
    expect(screen.getByText(/does not match/i)).toBeInTheDocument();
  });

  it("shows the red failure state when the seal doesn't match the hash on screen", async () => {
    renderWithQuery(
      <ProvenancePanel reel={{ ...reel, manifest_hash: "f".repeat(64) }} />,
    );

    await userEvent.click(
      screen.getByRole("button", { name: /verify provenance/i }),
    );

    expect(await screen.findByText(/verification failed/i)).toBeInTheDocument();
    expect(screen.getByText(/on screen/i)).toBeInTheDocument();
  });

  it("is honest — not alarmist — when the manifest isn't fetchable (404)", async () => {
    stubManifestFetch('{"detail":"no reel"}', 404);
    renderWithQuery(<ProvenancePanel reel={reel} />);

    await userEvent.click(
      screen.getByRole("button", { name: /verify provenance/i }),
    );

    expect(await screen.findByText(/can't verify here/i)).toBeInTheDocument();
    expect(screen.queryByText(/verification failed/i)).not.toBeInTheDocument();
  });
});
