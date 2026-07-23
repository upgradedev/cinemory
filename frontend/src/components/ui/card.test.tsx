import { createRef } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./card";

describe("card primitives", () => {
  it("renders the full composed card with all sub-parts", () => {
    render(
      <Card className="card-x">
        <CardHeader className="head-x">
          <CardTitle className="title-x">Sealed reel</CardTitle>
          <CardDescription className="desc-x">Provenance ready</CardDescription>
        </CardHeader>
        <CardContent className="content-x">body</CardContent>
      </Card>,
    );
    expect(screen.getByText("Sealed reel")).toBeInTheDocument();
    expect(screen.getByText("Provenance ready")).toBeInTheDocument();
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("merges caller classNames onto each primitive", () => {
    const { container } = render(
      <Card className="card-x">
        <CardHeader className="head-x">
          <CardTitle className="title-x">t</CardTitle>
          <CardDescription className="desc-x">d</CardDescription>
        </CardHeader>
        <CardContent className="content-x">c</CardContent>
      </Card>,
    );
    for (const cls of [".card-x", ".head-x", ".title-x", ".desc-x", ".content-x"]) {
      expect(container.querySelector(cls)).not.toBeNull();
    }
  });

  it("forwards a ref to the underlying Card element", () => {
    const ref = createRef<HTMLDivElement>();
    render(<Card ref={ref}>ref-target</Card>);
    expect(ref.current).toBeInstanceOf(HTMLDivElement);
    expect(ref.current?.textContent).toBe("ref-target");
  });
});
