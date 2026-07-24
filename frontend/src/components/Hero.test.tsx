import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Hero } from "./Hero";

describe("<Hero />", () => {
  it("renders the cinematic headline and features", () => {
    render(<Hero onStart={() => {}} />);
    expect(screen.getByText(/made into film/i)).toBeInTheDocument();
    expect(screen.getByText(/Provenance-sealed/i)).toBeInTheDocument();
  });

  it("fires onStart when the CTA is clicked", async () => {
    const onStart = vi.fn();
    render(<Hero onStart={onStart} />);
    await userEvent.click(screen.getByRole("button", { name: /create your reel/i }));
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("hides the sample CTA unless onTrySamples is provided", () => {
    render(<Hero onStart={() => {}} />);
    expect(
      screen.queryByRole("button", { name: /try with sample photos/i }),
    ).not.toBeInTheDocument();
  });

  it("fires onTrySamples from the secondary CTA when provided", async () => {
    const onTrySamples = vi.fn().mockResolvedValue(undefined);
    render(<Hero onStart={() => {}} onTrySamples={onTrySamples} />);
    await userEvent.click(
      screen.getByRole("button", { name: /try with sample photos/i }),
    );
    expect(onTrySamples).toHaveBeenCalledOnce();
  });
});
