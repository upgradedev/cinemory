import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReelLinkNotFound } from "./ReelLinkNotFound";

describe("<ReelLinkNotFound />", () => {
  it("says plainly that the link leads nowhere and offers a way forward", () => {
    render(<ReelLinkNotFound onStartNew={vi.fn()} />);
    expect(
      screen.getByRole("heading", { name: /couldn.t find that reel/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/may be mistyped/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /start a new reel/i }),
    ).toBeInTheDocument();
  });

  it("hands the fresh start back to its caller", async () => {
    const onStartNew = vi.fn();
    render(<ReelLinkNotFound onStartNew={onStartNew} />);
    await userEvent.click(screen.getByRole("button", { name: /start a new reel/i }));
    expect(onStartNew).toHaveBeenCalledTimes(1);
  });

  it("keeps a full tap target on the only control on the screen", () => {
    render(<ReelLinkNotFound onStartNew={vi.fn()} />);
    // jsdom has no layout, so the 44px floor is asserted on the class that
    // sets it here and measured for real by the responsive e2e.
    expect(
      screen.getByRole("button", { name: /start a new reel/i }).className,
    ).toMatch(/min-h-11/);
  });
});
