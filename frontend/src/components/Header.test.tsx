import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Header } from "./Header";
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

describe("<Header />", () => {
  it("does not show a developer-facing health badge once the backend resolves healthy", async () => {
    const healthSpy = vi.spyOn(cinemoryApi, "health").mockResolvedValue({
      status: "ok",
      service: "cinemory",
      mode: "live",
    });
    renderHeader();
    await waitFor(() => expect(healthSpy).toHaveBeenCalled());
    // A normal visitor should never see "API live" / internal mode strings —
    // the healthy path renders no ops-facing badge at all (the health check
    // itself still ran, above; only its user-facing badge is gone).
    expect(screen.queryByText(/API live/i)).not.toBeInTheDocument();
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
