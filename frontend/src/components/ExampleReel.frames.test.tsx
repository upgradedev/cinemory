import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExampleReel } from "./ExampleReel";

// Canvas is unavailable in jsdom, so stub the scene renderer to feed frames and
// exercise the animated (non-fallback) render path.
const mockRender = vi.fn();
vi.mock("@/lib/sample-photos", () => ({
  renderSampleSceneDataUrls: () => mockRender(),
}));

beforeEach(() => mockRender.mockReset());
afterEach(() => vi.unstubAllGlobals());

describe("<ExampleReel /> — frames render", () => {
  it("renders the animated preview with an accessible label and play badge", () => {
    mockRender.mockReturnValue(["data:image/jpeg;base64,a", "data:image/jpeg;base64,b"]);
    render(<ExampleReel />);
    expect(
      screen.getByRole("img", { name: /example cinemory reel/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/example reel/i)).toBeInTheDocument();
  });

  it("holds a single frame under prefers-reduced-motion", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    mockRender.mockReturnValue(["data:image/jpeg;base64,a", "data:image/jpeg;base64,b"]);
    render(<ExampleReel />);
    expect(
      screen.getByRole("img", { name: /example cinemory reel/i }),
    ).toBeInTheDocument();
  });

  it("falls back when the renderer yields no frames", () => {
    mockRender.mockReturnValue([]);
    render(<ExampleReel />);
    expect(
      screen.getByRole("img", { name: /filmstrip preview/i }),
    ).toBeInTheDocument();
  });
});
