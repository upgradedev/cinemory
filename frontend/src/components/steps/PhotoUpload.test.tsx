import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PhotoUpload } from "./PhotoUpload";
import { useReelStore } from "@/store/useReelStore";
import { generateSamplePhotos } from "@/lib/sample-photos";

// The generator itself is covered in lib/sample-photos.test.ts; here we mock
// it (jsdom has no canvas backend) and assert the UI wiring: one click must
// push real File objects through the exact same store path as user uploads.
vi.mock("@/lib/sample-photos", () => ({
  generateSamplePhotos: vi.fn(async () =>
    Array.from(
      { length: 5 },
      (_, i) =>
        new File([new Uint8Array([137, 80, 78, 71, i])], `cinemory-sample-${i + 1}.png`, {
          type: "image/png",
        }),
    ),
  ),
}));

beforeEach(() => {
  useReelStore.getState().reset();
  vi.mocked(generateSamplePhotos).mockClear();
});

describe("<PhotoUpload /> — sample photos fast path", () => {
  it("offers the one-click sample set with honest helper copy", () => {
    render(<PhotoUpload />);
    expect(
      screen.getByRole("button", { name: /try with sample photos/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no photos handy\? use our synthetic sample set\./i),
    ).toBeInTheDocument();
  });

  it("fills the storyboard through the regular photo store on click", async () => {
    render(<PhotoUpload />);
    await userEvent.click(
      screen.getByRole("button", { name: /try with sample photos/i }),
    );

    expect(generateSamplePhotos).toHaveBeenCalledTimes(1);
    expect(useReelStore.getState().photos).toHaveLength(5);
    // Thumbnails render like any user upload (same LocalPhoto shape).
    expect(await screen.findByAltText("cinemory-sample-1.png")).toBeInTheDocument();
    expect(
      screen.getByText((_, el) => el?.textContent === "5 photos · drag to reorder"),
    ).toBeInTheDocument();
    // The step CTA is now enabled and its blocker hint is gone.
    expect(
      screen.getByRole("button", { name: /choose an occasion/i }),
    ).toBeEnabled();
    expect(
      screen.queryByText(/add at least 1 photo to continue/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces a generation failure as a visible alert", async () => {
    vi.mocked(generateSamplePhotos).mockRejectedValueOnce(
      new Error("Canvas 2D is not supported in this browser."),
    );
    render(<PhotoUpload />);
    await userEvent.click(
      screen.getByRole("button", { name: /try with sample photos/i }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/canvas 2d/i);
    expect(useReelStore.getState().photos).toHaveLength(0);
  });
});

describe("<PhotoUpload /> — disabled-CTA guidance", () => {
  it("explains WHY the step CTA is disabled and wires it via aria-describedby", () => {
    render(<PhotoUpload />);
    const cta = screen.getByRole("button", { name: /choose an occasion/i });
    expect(cta).toBeDisabled();
    const hint = screen.getByText(/add at least 1 photo to continue/i);
    expect(cta).toHaveAttribute("aria-describedby", hint.id);
  });
});
