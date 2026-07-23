import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Footer } from "./Footer";

describe("<Footer />", () => {
  it("shows the current year and the provenance promise", () => {
    render(<Footer />);
    expect(
      screen.getByText(new RegExp(String(new Date().getFullYear()))),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/sealed with verifiable SHA-256 provenance/i),
    ).toBeInTheDocument();
  });

  it("links to the public repository, opening in a new tab safely", () => {
    render(<Footer />);
    const link = screen.getByRole("link", {
      name: /github\.com\/upgradedev\/cinemory/i,
    });
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/upgradedev/cinemory",
    );
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
