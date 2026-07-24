import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Stepper } from "./Stepper";

describe("<Stepper />", () => {
  it("labels every wizard step", () => {
    render(<Stepper current="upload" />);
    for (const label of ["Photos", "Occasion", "Generate", "Reel"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("marks the current step with aria-current and numbers the pending ones", () => {
    render(<Stepper current="occasion" />);
    // "Occasion" is index 1 → its <li> carries aria-current="step".
    const activeItem = screen.getByText("2").closest("li");
    expect(activeItem).toHaveAttribute("aria-current", "step");
    // A later, not-yet-reached step still shows its ordinal number.
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders completed steps as checkmarks, not numbers (final step active)", () => {
    render(<Stepper current="result" />);
    // At the last step, the first three are done → their ordinals are replaced
    // by check icons, so numbers 1–3 are no longer in the document.
    expect(screen.queryByText("1")).not.toBeInTheDocument();
    expect(screen.queryByText("2")).not.toBeInTheDocument();
    expect(screen.queryByText("3")).not.toBeInTheDocument();
    // The active (4th) step keeps its number; its <li> is the current step.
    expect(screen.getByText("4").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
  });
});
