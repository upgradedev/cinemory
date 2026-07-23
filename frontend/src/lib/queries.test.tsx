import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import {
  useCreateReel,
  useHealth,
  useManifest,
  useOccasions,
  useUploadReel,
} from "./queries";
import { cinemoryApi, type Occasion, type ReelResponse } from "./api";

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

const OCCASION: Occasion = {
  key: "wedding",
  label: "Wedding",
  music_style: "dreamy",
  tempo: 90,
  seconds_per_clip: 3,
  transition: "cross-dissolve",
  title_style: "serif",
  aspect_ratio: "16:9",
};

const REEL: ReelResponse = {
  reel_name: "demo",
  occasion: "wedding",
  reel_url: "b2://bucket/demo.mp4",
  reel_sha256: "a".repeat(64),
  manifest_uri: "b2://bucket/m.json",
  manifest_hash: "b".repeat(64),
  steps: 4,
};

afterEach(() => vi.restoreAllMocks());

describe("useHealth / useOccasions", () => {
  it("useHealth surfaces the backend mode", async () => {
    vi.spyOn(cinemoryApi, "health").mockResolvedValue({
      status: "ok",
      service: "cinemory",
      mode: "offline",
    });
    const { result } = renderHook(() => useHealth(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.mode).toBe("offline");
  });

  it("useOccasions returns the presets", async () => {
    vi.spyOn(cinemoryApi, "occasions").mockResolvedValue([OCCASION]);
    const { result } = renderHook(() => useOccasions(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([OCCASION]);
  });
});

describe("useManifest", () => {
  it("stays disabled (never fetches) when name is null", () => {
    const spy = vi.spyOn(cinemoryApi, "manifest");
    const { result } = renderHook(() => useManifest(null), {
      wrapper: wrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
    expect(spy).not.toHaveBeenCalled();
  });

  it("fetches the manifest once a name is supplied", async () => {
    const manifest = { reel_name: "demo", steps: [] } as never;
    vi.spyOn(cinemoryApi, "manifest").mockResolvedValue(manifest);
    const { result } = renderHook(() => useManifest("demo"), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(cinemoryApi.manifest).toHaveBeenCalledWith("demo");
  });
});

describe("reel mutations prime the manifest cache", () => {
  it("useCreateReel resolves the created reel", async () => {
    vi.spyOn(cinemoryApi, "createReel").mockResolvedValue(REEL);
    const { result } = renderHook(() => useCreateReel(), { wrapper: wrapper() });
    result.current.mutate({
      name: "demo",
      occasion: "wedding",
      chapters: 2,
      per_chapter: 2,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(REEL);
  });

  it("useUploadReel resolves the uploaded reel", async () => {
    vi.spyOn(cinemoryApi, "uploadReel").mockResolvedValue(REEL);
    const { result } = renderHook(() => useUploadReel(), { wrapper: wrapper() });
    result.current.mutate({
      name: "demo",
      occasion: "wedding",
      chapters: 2,
      files: [new File([new Uint8Array([1])], "a.png", { type: "image/png" })],
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(REEL);
  });
});
