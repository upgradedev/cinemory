import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Studio } from "./Studio";
import { useReelStore } from "@/store/useReelStore";
import type { ReelResponse } from "@/lib/api";

// Isolate Studio's own logic (step switching + the generate→result handoff) by
// stubbing the four heavy step screens. Each stub is a tiny marker; the
// GenerateReel stub also exposes a button that fires onComplete with a reel.
const FAKE_REEL: ReelResponse = {
  reel_name: "sealed-demo",
  occasion: "wedding",
  reel_url: null,
  reel_sha256: "a".repeat(64),
  manifest_uri: null,
  manifest_hash: "b".repeat(64),
  steps: 4,
};

vi.mock("./steps/PhotoUpload", () => ({
  PhotoUpload: () => <div>stub-photo-upload</div>,
}));
vi.mock("./steps/OccasionPicker", () => ({
  OccasionPicker: () => <div>stub-occasion-picker</div>,
}));
vi.mock("./steps/GenerateReel", () => ({
  GenerateReel: ({ onComplete }: { onComplete: (r: ReelResponse) => void }) => (
    <button onClick={() => onComplete(FAKE_REEL)}>stub-finish-generate</button>
  ),
}));
vi.mock("./steps/ReelResult", () => ({
  ReelResult: ({ reel }: { reel: ReelResponse }) => (
    <div>stub-reel-result: {reel.reel_name}</div>
  ),
}));

beforeEach(() => useReelStore.getState().reset());
afterEach(() => vi.restoreAllMocks());

describe("<Studio /> — step routing", () => {
  it("renders the upload step first, with the progress stepper", () => {
    render(<Studio />);
    expect(screen.getByText("stub-photo-upload")).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: /progress/i }),
    ).toBeInTheDocument();
    // The aria-live status announces the current step for screen readers.
    expect(screen.getByRole("status")).toHaveTextContent(/step 1 of 4/i);
  });

  it("shows the occasion step when the store advances", () => {
    useReelStore.getState().goTo("occasion");
    render(<Studio />);
    expect(screen.getByText("stub-occasion-picker")).toBeInTheDocument();
  });

  it("hands the finished reel from generate to the result screen", async () => {
    useReelStore.getState().goTo("generate");
    render(<Studio />);
    await userEvent.click(
      screen.getByRole("button", { name: /stub-finish-generate/i }),
    );
    expect(useReelStore.getState().step).toBe("result");
    // AnimatePresence mode="wait" swaps children on the next tick, so await it.
    expect(await screen.findByText(/stub-reel-result/i)).toHaveTextContent(
      "sealed-demo",
    );
  });

  it("falls back to the upload step at result when no reel is present", () => {
    useReelStore.getState().goTo("result");
    render(<Studio />);
    // No reel was produced in this session → guard renders PhotoUpload again.
    expect(screen.getByText("stub-photo-upload")).toBeInTheDocument();
  });
});
