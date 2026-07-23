import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header, modeTooltip } from "./Header";
import { cinemoryApi } from "@/lib/api";

function renderHeader() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <Header />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("modeTooltip", () => {
  it("explains the live and offline modes in plain English", () => {
    expect(modeTooltip("live")).toMatch(/real B2 storage/i);
    expect(modeTooltip("offline")).toMatch(/deterministic backends/i);
    // Unknown modes echo the raw value so nothing is hidden.
    expect(modeTooltip("staging")).toContain("staging");
  });
});

describe("<Header />", () => {
  it("shows the live API badge with its mode once health resolves", async () => {
    vi.spyOn(cinemoryApi, "health").mockResolvedValue({
      status: "ok",
      service: "cinemory",
      mode: "live",
    });
    renderHeader();
    // The badge's own text combines the static label with the live mode value.
    expect(await screen.findByText(/API live/)).toHaveTextContent("live");
    // The brand wordmark and home link are always present.
    expect(screen.getByLabelText(/cinemory home/i)).toBeInTheDocument();
  });

  it("shows an offline badge when the backend is unreachable", async () => {
    vi.spyOn(cinemoryApi, "health").mockRejectedValue(new Error("down"));
    renderHeader();
    await waitFor(() =>
      expect(screen.getByText(/API offline/i)).toBeInTheDocument(),
    );
  });
});
