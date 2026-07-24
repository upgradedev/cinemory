import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HowItWorks } from "./HowItWorks";

describe("<HowItWorks />", () => {
  it("names all three steps in order with a labelled section heading", () => {
    render(<HowItWorks />);
    expect(
      screen.getByRole("heading", { name: /how it works/i }),
    ).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(screen.getByText(/add your photos/i)).toBeInTheDocument();
    expect(screen.getByText(/pick an occasion/i)).toBeInTheDocument();
    expect(screen.getByText(/get a sealed reel/i)).toBeInTheDocument();
    expect(screen.getByText("Step 1")).toBeInTheDocument();
    expect(screen.getByText("Step 3")).toBeInTheDocument();
  });
});
