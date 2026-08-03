import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OccasionPicker } from "./OccasionPicker";
import { useReelStore } from "@/store/useReelStore";

beforeEach(() => {
  useReelStore.getState().reset();
  // Quiet 404 keeps the occasions query in a harmless error state — the
  // footer CTA under test renders regardless.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "not found" }),
    } as Response),
  );
});

afterEach(() => vi.unstubAllGlobals());

function renderPicker() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OccasionPicker />
    </QueryClientProvider>,
  );
}

describe("<OccasionPicker /> — disabled-CTA guidance", () => {
  it("explains WHY the generate CTA is disabled and wires it via aria-describedby", () => {
    renderPicker();
    const cta = screen.getByRole("button", { name: /generate my reel/i });
    expect(cta).toBeDisabled();
    const hint = screen.getByText(/pick an occasion to continue/i);
    expect(cta).toHaveAttribute("aria-describedby", hint.id);
  });

  it("drops the hint once an occasion is picked", () => {
    useReelStore.getState().setOccasion("wedding");
    renderPicker();
    expect(screen.getByRole("button", { name: /generate my reel/i })).toBeEnabled();
    expect(
      screen.queryByText(/pick an occasion to continue/i),
    ).not.toBeInTheDocument();
  });
});

describe("<OccasionPicker /> — the wait, said before it starts", () => {
  function imageFile(name: string): File {
    return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
  }

  it("estimates the wait from the photo count on the last screen before the run", () => {
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    useReelStore.getState().setOccasion("wedding");
    renderPicker();
    expect(
      screen.getByText(/1 photo usually takes about 6 minutes\./i),
    ).toBeInTheDocument();
  });

  it("moves with the count, so it is never a fixed string", () => {
    // Two photos still cost one wave of concurrent calls, so the wait is the
    // same as one photo. The SENTENCE still has to agree with the count.
    useReelStore.getState().addPhotos([imageFile("a.png"), imageFile("b.png")]);
    useReelStore.getState().setOccasion("wedding");
    renderPicker();
    expect(
      screen.getByText(/2 photos usually take about 6 minutes\./i),
    ).toBeInTheDocument();
  });

  it("keeps the blocker hint, not the estimate, while no occasion is picked", () => {
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    renderPicker();
    expect(screen.getByText(/pick an occasion to continue/i)).toBeInTheDocument();
    expect(screen.queryByText(/usually takes/i)).not.toBeInTheDocument();
  });
});
