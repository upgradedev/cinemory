import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HashChip } from "./HashChip";

describe("<HashChip />", () => {
  it("shows a truncated hash and copies the full value", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    const full = "0123456789abcdef0123456789abcdef";
    render(<HashChip hash={full} label="manifest" />);

    expect(screen.getByText("01234567…89abcdef")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    expect(writeText).toHaveBeenCalledWith(full);
  });

  it("is disabled with no hash", () => {
    render(<HashChip hash={null} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
