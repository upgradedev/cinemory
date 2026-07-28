import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MyReels } from "./MyReels";
import { ApiError, cinemoryApi, type LibraryReel, type Manifest } from "@/lib/api";

// MyReels reads the current user via useAuthUser (lib/auth) but talks to the
// backend through cinemoryApi (lib/api) via the real queries.ts hooks —
// mirrors how Header.test.tsx mocks cinemoryApi.health rather than useHealth,
// so react-query's real loading/success/error machinery is exercised.
const mocks = vi.hoisted(() => ({ useAuthUser: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuthUser: mocks.useAuthUser }));

const SIGNED_IN = {
  user: { uid: "u1", displayName: "Ada", email: "ada@example.com", photoURL: null },
  loading: false,
};

function renderMyReels(onBack: () => void = vi.fn()) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MyReels onBack={onBack} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("<MyReels /> — loading and empty", () => {
  it("shows a loading skeleton while the library is being fetched, then the empty state", async () => {
    mocks.useAuthUser.mockReturnValue(SIGNED_IN);
    let resolveLibrary!: (value: LibraryReel[]) => void;
    const pending = new Promise<LibraryReel[]>((resolve) => {
      resolveLibrary = resolve;
    });
    vi.spyOn(cinemoryApi, "myLibrary").mockReturnValue(pending);

    const { container } = renderMyReels();
    expect(container.querySelector(".animate-pulse")).not.toBeNull();

    resolveLibrary([]);
    await waitFor(() =>
      expect(screen.getByText(/you have not saved any reels yet/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /delete all my data/i })).not.toBeInTheDocument();
  });
});

describe("<MyReels /> — list", () => {
  const REELS: LibraryReel[] = [
    {
      reel_name: "wedding-2024",
      manifest_hash: "a".repeat(16),
      created_at: "2026-01-15T10:00:00Z",
      updated_at: null,
    },
    { reel_name: "graduation", manifest_hash: null, created_at: null, updated_at: null },
  ];

  beforeEach(() => {
    mocks.useAuthUser.mockReturnValue(SIGNED_IN);
    vi.spyOn(cinemoryApi, "myLibrary").mockResolvedValue(REELS);
  });

  it("renders every saved reel by name", async () => {
    renderMyReels();
    await waitFor(() => expect(screen.getByText("wedding-2024")).toBeInTheDocument());
    expect(screen.getByText("graduation")).toBeInTheDocument();
  });

  it("shows the delete-all control once reels exist", async () => {
    renderMyReels();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /delete all my data/i })).toBeInTheDocument(),
    );
  });

  it("shows 'Date unknown' for a reel with no created_at", async () => {
    renderMyReels();
    await waitFor(() => expect(screen.getByText("graduation")).toBeInTheDocument());
    const row = screen.getByText("graduation").closest("li") as HTMLElement;
    expect(within(row).getByText("Date unknown")).toBeInTheDocument();
  });

  it("expands a row to fetch and show its provenance", async () => {
    const manifest: Manifest = {
      schema: "v1",
      reel_name: "wedding-2024",
      occasion: "wedding",
      occasion_style: {},
      reel_asset: { modality: "video", sha256: "c".repeat(64), size_bytes: 5 },
      steps: [
        {
          provider: "genblaze",
          model: "m",
          prompt: "x",
          modality: "video",
          params: {},
          started_at: "t0",
          finished_at: "t1",
          asset: { modality: "video", sha256: "c".repeat(64), size_bytes: 5 },
        },
      ],
      manifest_hash: "a".repeat(16),
    };
    const manifestSpy = vi.spyOn(cinemoryApi, "manifest").mockResolvedValue(manifest);
    renderMyReels();
    await waitFor(() => expect(screen.getByText("wedding-2024")).toBeInTheDocument());
    const row = screen.getByText("wedding-2024").closest("li") as HTMLElement;

    expect(manifestSpy).not.toHaveBeenCalled(); // never fetched before expanding
    await userEvent.click(within(row).getByRole("button", { name: /view provenance/i }));

    await waitFor(() => expect(within(row).getByText("wedding")).toBeInTheDocument());
    expect(within(row).getByText("1 generative steps")).toBeInTheDocument();
    expect(manifestSpy).toHaveBeenCalledWith("wedding-2024");

    // Collapsing and re-expanding must not refetch (staleTime: Infinity).
    await userEvent.click(within(row).getByRole("button", { name: /hide provenance/i }));
    await userEvent.click(within(row).getByRole("button", { name: /view provenance/i }));
    expect(manifestSpy).toHaveBeenCalledTimes(1);
  });

  it("shows an honest not-available note when the manifest resolves to null (404)", async () => {
    vi.spyOn(cinemoryApi, "manifest").mockResolvedValue(null);
    renderMyReels();
    await waitFor(() => expect(screen.getByText("graduation")).toBeInTheDocument());
    const row = screen.getByText("graduation").closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: /view provenance/i }));
    await waitFor(() =>
      expect(within(row).getByText(/not available on this deployment/i)).toBeInTheDocument(),
    );
  });

  it("shows an honest error line when the manifest fetch itself fails", async () => {
    vi.spyOn(cinemoryApi, "manifest").mockRejectedValue(new Error("down"));
    renderMyReels();
    await waitFor(() => expect(screen.getByText("graduation")).toBeInTheDocument());
    const row = screen.getByText("graduation").closest("li") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: /view provenance/i }));
    await waitFor(() =>
      expect(within(row).getByText(/could not load this reel's details/i)).toBeInTheDocument(),
    );
  });
});

describe("<MyReels /> — 401 graceful degrade vs generic error", () => {
  beforeEach(() => mocks.useAuthUser.mockReturnValue(SIGNED_IN));

  it("shows the honest degrade note on a 401 (backend multitenancy not enabled here)", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockRejectedValue(new ApiError("nope", 401));
    renderMyReels();
    await waitFor(() =>
      expect(
        screen.getByText(/sign-in library is not available on this deployment/i),
      ).toBeInTheDocument(),
    );
  });

  it("shows a generic retry message on a non-401 ApiError", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockRejectedValue(new ApiError("boom", 500));
    renderMyReels();
    await waitFor(() =>
      expect(screen.getByText(/could not load your reels right now/i)).toBeInTheDocument(),
    );
  });

  it("shows the same generic message for a non-ApiError failure (e.g. a network error)", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockRejectedValue(new Error("network down"));
    renderMyReels();
    await waitFor(() =>
      expect(screen.getByText(/could not load your reels right now/i)).toBeInTheDocument(),
    );
    expect(
      screen.queryByText(/sign-in library is not available on this deployment/i),
    ).not.toBeInTheDocument();
  });
});

describe("<MyReels /> — delete all my data", () => {
  const REELS: LibraryReel[] = [
    { reel_name: "r1", manifest_hash: null, created_at: null, updated_at: null },
  ];

  beforeEach(() => mocks.useAuthUser.mockReturnValue(SIGNED_IN));

  it("opens the confirm dialog, calls DELETE /me/data on confirm, and refreshes to the empty state", async () => {
    const myLibrary = vi
      .spyOn(cinemoryApi, "myLibrary")
      .mockResolvedValueOnce(REELS)
      .mockResolvedValueOnce([]);
    const deleteMyData = vi.spyOn(cinemoryApi, "deleteMyData").mockResolvedValue({ deleted: 1 });
    renderMyReels();

    await waitFor(() => expect(screen.getByText("r1")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /delete all my data/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /delete everything/i }));
    expect(deleteMyData).toHaveBeenCalledTimes(1);

    await waitFor(() =>
      expect(screen.getByText(/all your data has been deleted/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/you have not saved any reels yet/i)).toBeInTheDocument(),
    );
    expect(myLibrary).toHaveBeenCalledTimes(2); // initial fetch + refetch after invalidation
  });

  it("does not call DELETE /me/data when the dialog is cancelled", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockResolvedValue(REELS);
    const deleteMyData = vi.spyOn(cinemoryApi, "deleteMyData");
    renderMyReels();

    await waitFor(() => expect(screen.getByText("r1")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /delete all my data/i }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(deleteMyData).not.toHaveBeenCalled();
  });

  it("shows an error inside the dialog and keeps it open when the delete fails", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockResolvedValue(REELS);
    vi.spyOn(cinemoryApi, "deleteMyData").mockRejectedValue(new Error("network down"));
    renderMyReels();

    await waitFor(() => expect(screen.getByText("r1")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /delete all my data/i }));
    await userEvent.click(screen.getByRole("button", { name: /delete everything/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/could not delete your data/i),
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText(/all your data has been deleted/i)).not.toBeInTheDocument();
  });

  it("clears the pending auto-dismiss timer on unmount without throwing", async () => {
    vi.spyOn(cinemoryApi, "myLibrary").mockResolvedValueOnce(REELS).mockResolvedValueOnce([]);
    vi.spyOn(cinemoryApi, "deleteMyData").mockResolvedValue({ deleted: 1 });
    const { unmount } = renderMyReels();

    await waitFor(() => expect(screen.getByText("r1")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /delete all my data/i }));
    await userEvent.click(screen.getByRole("button", { name: /delete everything/i }));
    await waitFor(() =>
      expect(screen.getByText(/all your data has been deleted/i)).toBeInTheDocument(),
    );

    expect(() => unmount()).not.toThrow();
  });
});

describe("<MyReels /> — back navigation and the sign-out guard", () => {
  it("calls onBack when the Back control is clicked", async () => {
    mocks.useAuthUser.mockReturnValue(SIGNED_IN);
    vi.spyOn(cinemoryApi, "myLibrary").mockResolvedValue([]);
    const onBack = vi.fn();
    renderMyReels(onBack);
    await userEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("calls onBack automatically once auth resolves to signed-out", async () => {
    mocks.useAuthUser.mockReturnValue({ user: null, loading: false });
    const onBack = vi.fn();
    renderMyReels(onBack);
    await waitFor(() => expect(onBack).toHaveBeenCalledTimes(1));
  });

  it("does not call onBack while the initial auth state is still loading", () => {
    mocks.useAuthUser.mockReturnValue({ user: null, loading: true });
    const onBack = vi.fn();
    renderMyReels(onBack);
    expect(onBack).not.toHaveBeenCalled();
  });
});
