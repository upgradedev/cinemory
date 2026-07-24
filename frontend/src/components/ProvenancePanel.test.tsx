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

// Route the mocked fetch by URL: `GET /reels/{name}` (react-query manifest +
// the in-browser seal recompute) serves the manifest bytes; `GET
// /reels/{name}/verify` serves the server-side receipt (or 404 when none is
// configured, exercising the honest-degrade path).
function stubApi(opts: {
  manifest?: string;
  manifestStatus?: number;
  receipt?: unknown;
  receiptReject?: boolean;
} = {}) {
  const { manifest = goldenRaw, manifestStatus = 200, receipt, receiptReject } = opts;
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/verify")) {
        if (receiptReject) return Promise.reject(new TypeError("network down"));
        if (receipt === undefined) return Promise.resolve({ ok: false, status: 404 } as Response);
        return Promise.resolve({ ok: true, status: 200, json: async () => receipt } as Response);
      }
      return Promise.resolve({
        ok: manifestStatus >= 200 && manifestStatus < 300,
        status: manifestStatus,
        text: async () => manifest,
        json: async () => JSON.parse(manifest),
      } as Response);
    }),
  );
}

function stubManifestFetch(body: string, status = 200) {
  stubApi({ manifest: body, manifestStatus: status });
}

const okReceipt = {
  success: true,
  digest: "a".repeat(64),
  checks: [
    { id: "seal.manifest_hash", label: "Manifest seal recomputes (SHA-256)", passed: true, evidence: "seal ok" },
    { id: "artifact.reel", label: "Reel bytes match the sealed hash", passed: true, evidence: "matches" },
  ],
};

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

describe("<ProvenancePanel /> — server-side aggregate re-verification", () => {
  it("renders each named check with a text pass label after Verify", async () => {
    stubApi({ receipt: okReceipt });
    renderWithQuery(<ProvenancePanel reel={reel} />);

    await userEvent.click(screen.getByRole("button", { name: /verify provenance/i }));

    expect(
      await screen.findByText(/2\/2 checks passed — all verified/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/reel bytes match the sealed hash/i)).toBeInTheDocument();
    // Non-colour-only: an explicit textual "Passed" label per check.
    expect(screen.getAllByText(/^passed$/i).length).toBeGreaterThanOrEqual(2);
  });

  it("shows a tamper-detected summary + a Failed label when a server check fails", async () => {
    stubApi({
      receipt: {
        ...okReceipt,
        success: false,
        checks: [
          okReceipt.checks[0],
          {
            id: "artifact.reel",
            label: "Reel bytes match the sealed hash",
            passed: false,
            evidence: "re-hashed stored reel does NOT match",
          },
        ],
      },
    });
    renderWithQuery(<ProvenancePanel reel={reel} />);

    await userEvent.click(screen.getByRole("button", { name: /verify provenance/i }));

    expect(await screen.findByText(/tamper detected/i)).toBeInTheDocument();
    expect(screen.getByText(/^failed$/i)).toBeInTheDocument();
  });

  it("honestly degrades (no red failure) when no receipt is served", async () => {
    stubApi({ receipt: undefined }); // GET /verify → 404
    renderWithQuery(<ProvenancePanel reel={reel} />);

    await userEvent.click(screen.getByRole("button", { name: /verify provenance/i }));

    expect(
      await screen.findByText(/doesn't serve a re-verification receipt/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/tamper detected/i)).not.toBeInTheDocument();
  });
});
