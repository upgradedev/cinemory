import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PhotoUpload } from "./PhotoUpload";
import { useReelStore } from "@/store/useReelStore";

function imageFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
}

beforeEach(() => useReelStore.getState().reset());

describe("<PhotoUpload /> — file input & dropzone", () => {
  it("adds files chosen through the hidden file input", async () => {
    render(<PhotoUpload />);
    const input = screen.getByLabelText(/choose photos/i);
    await userEvent.upload(input, [imageFile("a.png"), imageFile("b.png")]);
    expect(useReelStore.getState().photos).toHaveLength(2);
    expect(await screen.findByAltText("a.png")).toBeInTheDocument();
  });

  it("opens the native picker when Browse files is clicked", async () => {
    render(<PhotoUpload />);
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    await userEvent.click(screen.getByRole("button", { name: /browse files/i }));
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it("accepts photos dropped onto the dropzone (with drag hover state)", () => {
    const { container } = render(<PhotoUpload />);
    const dropzone = container.querySelector(
      '[class*="border-dashed"]',
    ) as HTMLElement;
    fireEvent.dragOver(dropzone);
    fireEvent.dragLeave(dropzone);
    fireEvent.drop(dropzone, {
      dataTransfer: { files: [imageFile("dropped.png")] },
    });
    expect(useReelStore.getState().photos).toHaveLength(1);
    expect(useReelStore.getState().photos[0]?.name).toBe("dropped.png");
  });
});

describe("<PhotoUpload /> — storyboard management", () => {
  it("removes a single photo and clears them all", async () => {
    useReelStore
      .getState()
      .addPhotos([imageFile("a.png"), imageFile("b.png")]);
    render(<PhotoUpload />);

    await userEvent.click(
      screen.getByRole("button", { name: /remove a\.png/i }),
    );
    expect(useReelStore.getState().photos).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: /clear all/i }));
    expect(useReelStore.getState().photos).toHaveLength(0);
    // Empty-state hint returns once the storyboard is cleared.
    expect(
      screen.getByText(/your selected photos will appear here/i),
    ).toBeInTheDocument();
  });

  it("reorders photos via drag and drop", () => {
    useReelStore
      .getState()
      .addPhotos([imageFile("first.png"), imageFile("second.png")]);
    render(<PhotoUpload />);

    const firstLi = screen.getByAltText("first.png").closest("li")!;
    const secondLi = screen.getByAltText("second.png").closest("li")!;
    fireEvent.dragStart(firstLi);
    fireEvent.dragOver(secondLi);
    fireEvent.drop(secondLi);
    fireEvent.dragEnd(firstLi);

    // "first" was dropped onto "second" → order flips.
    expect(useReelStore.getState().photos.map((p) => p.name)).toEqual([
      "second.png",
      "first.png",
    ]);
  });

  it("advances to the occasion step from the storyboard CTA", async () => {
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    render(<PhotoUpload />);
    const grid = screen.getByRole("list");
    expect(within(grid).getByAltText("a.png")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /choose an occasion/i }),
    );
    expect(useReelStore.getState().step).toBe("occasion");
  });
});
