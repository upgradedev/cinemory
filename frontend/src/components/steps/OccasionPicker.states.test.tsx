import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OccasionPicker } from "./OccasionPicker";
import { useReelStore } from "@/store/useReelStore";
import { cinemoryApi, type Occasion } from "@/lib/api";

function occ(key: string, label: string): Occasion {
  return {
    key,
    label,
    music_style: "warm strings",
    tempo: 96,
    seconds_per_clip: 3.5,
    transition: "cross-dissolve",
    title_style: "serif",
    aspect_ratio: "16:9",
  };
}

function renderPicker() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OccasionPicker />
    </QueryClientProvider>,
  );
}

beforeEach(() => useReelStore.getState().reset());
afterEach(() => vi.restoreAllMocks());

describe("<OccasionPicker /> — async states", () => {
  it("shows skeleton placeholders while occasions load", () => {
    // Never resolves → the query stays in its loading state.
    vi.spyOn(cinemoryApi, "occasions").mockReturnValue(new Promise(() => {}));
    const { container } = renderPicker();
    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(6);
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });

  it("shows an error state and retries on demand", async () => {
    const spy = vi
      .spyOn(cinemoryApi, "occasions")
      .mockRejectedValue(new Error("offline"));
    renderPicker();
    await waitFor(() =>
      expect(
        screen.getByText(/couldn’t load occasion presets/i),
      ).toBeInTheDocument(),
    );
    const before = spy.mock.calls.length;
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(spy.mock.calls.length).toBeGreaterThan(before),
    );
  });

  it("renders occasion cards, selects one and advances the wizard", async () => {
    vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([
      occ("wedding", "Wedding"), // known theme
      occ("mystery-gala", "Mystery Gala"), // falls back to the neutral theme
    ]);
    renderPicker();

    const wedding = await screen.findByRole("radio", { name: /wedding/i });
    expect(wedding).toHaveAttribute("aria-checked", "false");
    // Generate is blocked until an occasion is chosen.
    expect(
      screen.getByRole("button", { name: /generate my reel/i }),
    ).toBeDisabled();

    await userEvent.click(wedding);
    expect(useReelStore.getState().occasionKey).toBe("wedding");
    expect(
      await screen.findByRole("radio", { name: /wedding/i }),
    ).toHaveAttribute("aria-checked", "true");

    await userEvent.click(
      screen.getByRole("button", { name: /generate my reel/i }),
    );
    expect(useReelStore.getState().step).toBe("generate");
  });

  it("goes back to the upload step", async () => {
    vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([occ("wedding", "Wedding")]);
    renderPicker();
    await screen.findByRole("radio", { name: /wedding/i });
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(useReelStore.getState().step).toBe("upload");
  });
});
