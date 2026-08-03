import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { cinemoryApi } from "@/lib/api";
import { useReelStore } from "@/store/useReelStore";

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
  window.history.replaceState(null, "", window.location.pathname);
  useReelStore.getState().reset();
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

  it("enters the studio from the landing sample-photos CTA", async () => {
    renderApp();
    // jsdom has no canvas backend, so sample generation is skipped — but the
    // demo entry must still drop the visitor into the studio.
    await userEvent.click(
      screen.getByRole("button", { name: /try with sample photos/i }),
    );
    expect(
      await screen.findByRole("navigation", { name: /progress/i }),
    ).toBeInTheDocument();
  });
});

describe("<App /> — reopening a reel from its link", () => {
  it("resumes the reel the link names instead of starting blank", async () => {
    // The scenario this exists for: the tab that started this reel is gone,
    // but the reel carried on server-side and the link still finds it.
    const getJobSpy = vi
      .spyOn(cinemoryApi, "getReelJob")
      .mockReturnValue(new Promise(() => {}));
    window.location.hash = "#reel/PEYsghoylVNUrc2rNAdHJa6_";

    renderApp();

    expect(
      await screen.findByRole("heading", { name: /rolling/i }),
    ).toBeInTheDocument();
    expect(getJobSpy).toHaveBeenCalledWith("PEYsghoylVNUrc2rNAdHJa6_");
    // Straight to the generating step, not back to step 1.
    expect(useReelStore.getState().step).toBe("generate");
    // And the landing page is NOT what a returning visitor sees.
    expect(
      screen.queryByRole("button", { name: /create your reel/i }),
    ).not.toBeInTheDocument();
  });

  it("says plainly that a malformed link leads nowhere, without asking the server", () => {
    const getJobSpy = vi.spyOn(cinemoryApi, "getReelJob");
    window.location.hash = "#reel/not-a-real-id!!";

    renderApp();

    expect(
      screen.getByRole("heading", { name: /couldn.t find that reel/i }),
    ).toBeInTheDocument();
    // No spinner, no wizard, and no pointless round trip for an id that
    // cannot exist.
    expect(getJobSpy).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("offers a fresh start from a broken link, which clears the link too", async () => {
    window.location.hash = "#reel/nope!";
    renderApp();

    await userEvent.click(screen.getByRole("button", { name: /start a new reel/i }));

    expect(
      screen.getByRole("navigation", { name: /progress/i }),
    ).toBeInTheDocument();
    // A refresh after starting over must not reopen the broken link.
    expect(window.location.hash).toBe("");
  });

  it("ignores a hash that is not a route, such as the skip link's target", () => {
    window.location.hash = "#main-content";
    renderApp();
    expect(
      screen.getByRole("button", { name: /create your reel/i }),
    ).toBeInTheDocument();
  });
});
