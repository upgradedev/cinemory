import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PhotoUpload } from "./PhotoUpload";
import { useReelStore } from "@/store/useReelStore";
import { MAX_REEL_PHOTOS } from "@/lib/reel-budget";
import { generateSamplePhotos } from "@/lib/sample-photos";

// The generator itself is covered in lib/sample-photos.test.ts; here we mock
// it (jsdom has no canvas backend) and assert the UI wiring: one click must
// push real File objects through the exact same store path as user uploads,
// carrying descriptive alt text (not the filename).
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
  samplePhotoAlts: vi.fn(() =>
    Array.from({ length: 5 }, (_, i) => `Sample scene ${i + 1} description`),
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
    expect(useReelStore.getState().photos).toHaveLength(MAX_REEL_PHOTOS);
    // Thumbnails render with descriptive alt text, NOT the raw filename.
    expect(await screen.findByAltText("Sample scene 1 description")).toBeInTheDocument();
    expect(screen.queryByAltText("cinemory-sample-1.png")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        (_, el) => el?.textContent === `${MAX_REEL_PHOTOS} photos · drag to reorder`,
      ),
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

describe("<PhotoUpload /> — privacy note", () => {
  it("tells a visitor where their photos go before they upload anything", () => {
    render(<PhotoUpload />);
    expect(
      screen.getByText(/private Backblaze B2 bucket/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/no model captions or describes them/i)).toBeInTheDocument();
    // Must not overclaim that no AI ever touches the photo — the generation
    // provider does process it (to animate it); only captioning/description
    // is ruled out.
    expect(
      screen.getByText(/animated by our generation provider/i),
    ).toBeInTheDocument();
  });

  it("links to the fuller privacy section in the README", () => {
    render(<PhotoUpload />);
    const link = screen.getByRole("link", { name: /full privacy details/i });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/upgradedev/cinemory#your-photos-and-your-data",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
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

describe("<PhotoUpload /> — the photo cap, said out loud", () => {
  it("states the cap and that it belongs to the demo, not the product", () => {
    render(<PhotoUpload />);
    expect(
      screen.getByText(new RegExp(`up to ${MAX_REEL_PHOTOS} photos per reel here`, "i")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/limit of this demo, not of the reel maker/i),
    ).toBeInTheDocument();
  });

  it("tells the visitor when a bigger selection was shortened, and announces it", async () => {
    render(<PhotoUpload />);
    const input = screen.getByLabelText(/choose photos/i);
    await userEvent.upload(
      input,
      Array.from({ length: MAX_REEL_PHOTOS + 2 }, (_, i) =>
        new File([new Uint8Array([1, 2, 3])], `p${i}.png`, { type: "image/png" }),
      ),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/2 of the photos you picked were left out/i);
    expect(useReelStore.getState().photos).toHaveLength(MAX_REEL_PHOTOS);
  });

  it("shows no such notice when the selection fits", async () => {
    render(<PhotoUpload />);
    await userEvent.upload(
      screen.getByLabelText(/choose photos/i),
      new File([new Uint8Array([1, 2, 3])], "one.png", { type: "image/png" }),
    );
    expect(await screen.findByAltText("one.png")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
