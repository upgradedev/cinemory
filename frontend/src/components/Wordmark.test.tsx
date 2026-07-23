import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { Wordmark } from "./Wordmark";

describe("<Wordmark />", () => {
  it("renders the split Cine/mory brand mark", () => {
    const { container } = render(<Wordmark />);
    // The name is split across two spans (Cine + mory) for the gold gradient,
    // so assert on the combined text content of the wrapper.
    expect(container).toHaveTextContent("Cinemory");
  });

  it("merges a caller-supplied className onto the root", () => {
    const { container } = render(<Wordmark className="custom-mark" />);
    expect(container.querySelector(".custom-mark")).not.toBeNull();
  });
});
