import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { cinemoryApi } from "@/lib/api";

function renderApp() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <App />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.spyOn(cinemoryApi, "health").mockResolvedValue({
    status: "ok",
    service: "cinemory",
    mode: "offline",
  });
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
  window.location.hash = "";
});

describe("<App />", () => {
  it("lands on the hero and hides the studio wizard", () => {
    renderApp();
    expect(
      screen.getByRole("button", { name: /create your reel/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: /progress/i }),
    ).not.toBeInTheDocument();
  });

  it("enters the studio when the hero CTA is clicked", async () => {
    renderApp();
    await userEvent.click(
      screen.getByRole("button", { name: /create your reel/i }),
    );
    // The stepper (Studio-only) is now on screen and the page scrolled to top.
    expect(
      screen.getByRole("navigation", { name: /progress/i }),
    ).toBeInTheDocument();
    expect(window.scrollTo).toHaveBeenCalled();
  });

  it("deep-links straight into the studio on the #create hash", () => {
    window.location.hash = "#create";
    renderApp();
    expect(
      screen.getByRole("navigation", { name: /progress/i }),
    ).toBeInTheDocument();
  });
});
