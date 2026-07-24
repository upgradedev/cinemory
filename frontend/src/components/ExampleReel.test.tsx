import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExampleReel, ExampleReelFallback } from "./ExampleReel";

describe("<ExampleReel />", () => {
  it("falls back to the static filmstrip when Canvas 2D is unavailable", () => {
    // jsdom ships no canvas backend, so the real renderSampleSceneDataUrls
    // throws — exercising ExampleReel's try/catch fallback path for real.
    render(<ExampleReel />);
    expect(
      screen.getByRole("img", { name: /filmstrip preview/i }),
    ).toBeInTheDocument();
  });
});

describe("<ExampleReelFallback />", () => {
  it("shows a labelled four-chapter filmstrip", () => {
    render(<ExampleReelFallback />);
    expect(
      screen.getByRole("img", { name: /filmstrip preview/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ch.1")).toBeInTheDocument();
    expect(screen.getByText("Ch.4")).toBeInTheDocument();
  });
});
