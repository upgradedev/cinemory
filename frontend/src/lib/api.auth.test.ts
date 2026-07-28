import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// lib/api.ts imports ONLY `getIdToken` from lib/auth — mocking that single
// export here is complete for this file's purposes (see the codebase note:
// a partial mock of a module is only safe when it covers every export the
// code under test actually reaches, and this is the only one it reaches).
const mocks = vi.hoisted(() => ({ getIdToken: vi.fn() }));
vi.mock("./auth", () => ({ getIdToken: mocks.getIdToken }));

import { ApiError, cinemoryApi } from "./api";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

const REEL_BODY = {
  reel_name: "r",
  reel_url: null,
  reel_sha256: "a".repeat(64),
  manifest_uri: null,
  manifest_hash: "b".repeat(64),
  steps: 1,
};

afterEach(() => {
  vi.restoreAllMocks();
  mocks.getIdToken.mockReset();
});

describe("guest (getIdToken resolves null) — every reel call is byte-identical to before", () => {
  beforeEach(() => mocks.getIdToken.mockResolvedValue(null));

  it("createReel: headers carry Content-Type only, no Authorization key", async () => {
    const fetchMock = mockFetch(200, REEL_BODY);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.createReel({ name: "r", occasion: "wedding", chapters: 1, per_chapter: 1 });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("uploadReel: reaches fetch with only request()'s default header, no Authorization", async () => {
    const fetchMock = mockFetch(200, REEL_BODY);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.uploadReel({ name: "r", occasion: "wedding", chapters: 1, files: [] });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    // The caller omits the `headers` key entirely for a guest, so request()'s
    // own default survives untouched — byte-identical to the pre-auth call.
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  it("getReelJob: only request()'s default header reaches fetch, matching pre-auth behavior exactly", async () => {
    const fetchMock = mockFetch(200, { job_id: "j", status: "queued" });
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.getReelJob("j");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  it("manifest: the third (init) argument passed through is undefined", async () => {
    const manifestBody = {
      schema: "v1",
      reel_name: "r",
      occasion: "wedding",
      occasion_style: {},
      reel_asset: { modality: "video", sha256: "c".repeat(64), size_bytes: 10 },
      steps: [],
      manifest_hash: "d".repeat(64),
    };
    const fetchMock = mockFetch(200, manifestBody);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.manifest("r");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Accept: "application/json" });
  });

  it("submitReelJob: headers carry Content-Type only, no Authorization key", async () => {
    const fetchMock = mockFetch(202, { job_id: "j", status: "queued" });
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.submitReelJob({ name: "r", occasion: "wedding", chapters: 1, files: [] });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });
});

describe("signed in (getIdToken resolves a fresh token)", () => {
  beforeEach(() => mocks.getIdToken.mockResolvedValue("fresh-id-token"));

  it("createReel carries Authorization alongside Content-Type", async () => {
    const fetchMock = mockFetch(200, REEL_BODY);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.createReel({ name: "r", occasion: "wedding", chapters: 1, per_chapter: 1 });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer fresh-id-token",
    });
  });

  it("uploadReel carries Authorization without ever setting Content-Type (multipart boundary stays browser-set)", async () => {
    const fetchMock = mockFetch(200, REEL_BODY);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.uploadReel({ name: "r", occasion: "wedding", chapters: 1, files: [] });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer fresh-id-token");
    expect(headers["Content-Type"]).toBeUndefined();
    expect(init.body).toBeInstanceOf(FormData);
  });

  it("getReelJob carries Authorization", async () => {
    const fetchMock = mockFetch(200, { job_id: "j", status: "running" });
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.getReelJob("j");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-id-token" });
  });

  it("manifest carries Authorization", async () => {
    vi.stubGlobal("fetch", mockFetch(404, { detail: "nope" }));
    await expect(cinemoryApi.manifest("r")).resolves.toBeNull();
    const [, init] = (fetch as ReturnType<typeof mockFetch>).mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({ Authorization: "Bearer fresh-id-token" });
  });

  it("submitReelJob carries Authorization alongside Content-Type", async () => {
    const fetchMock = mockFetch(202, { job_id: "j", status: "queued" });
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.submitReelJob({ name: "r", occasion: "wedding", chapters: 1, files: [] });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer fresh-id-token",
    });
  });

  it("asks for a fresh token on every call — two calls, two distinct tokens", async () => {
    mocks.getIdToken.mockReset();
    mocks.getIdToken.mockResolvedValueOnce("token-A").mockResolvedValueOnce("token-B");
    const fetchMock = mockFetch(200, REEL_BODY);
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.createReel({ name: "r", occasion: "wedding", chapters: 1, per_chapter: 1 });
    await cinemoryApi.createReel({ name: "r2", occasion: "wedding", chapters: 1, per_chapter: 1 });
    expect(mocks.getIdToken).toHaveBeenCalledTimes(2);
    const first = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const second = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect((first.headers as Record<string, string>).Authorization).toBe("Bearer token-A");
    expect((second.headers as Record<string, string>).Authorization).toBe("Bearer token-B");
  });
});

describe("cinemoryApi.myLibrary", () => {
  it("returns the reels array on success and attaches Authorization", async () => {
    mocks.getIdToken.mockResolvedValue("lib-token");
    const fetchMock = mockFetch(200, {
      reels: [
        { reel_name: "a", manifest_hash: "h1", created_at: "2026-01-01T00:00:00Z", updated_at: null },
        { reel_name: "b", manifest_hash: null, created_at: null, updated_at: null },
      ],
    });
    vi.stubGlobal("fetch", fetchMock);
    const reels = await cinemoryApi.myLibrary();
    expect(reels).toHaveLength(2);
    expect(reels[0]?.reel_name).toBe("a");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/me/library");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer lib-token");
  });

  it("surfaces a 401 as ApiError (guest, or a token the backend rejects)", async () => {
    mocks.getIdToken.mockResolvedValue(null);
    vi.stubGlobal("fetch", mockFetch(401, { detail: "sign in required" }));
    const err = await cinemoryApi.myLibrary().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
  });
});

describe("cinemoryApi.deleteMyData", () => {
  it("sends DELETE with Authorization and returns the deleted count", async () => {
    mocks.getIdToken.mockResolvedValue("del-token");
    const fetchMock = mockFetch(200, { deleted: 3 });
    vi.stubGlobal("fetch", fetchMock);
    const result = await cinemoryApi.deleteMyData();
    expect(result).toEqual({ deleted: 3 });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/me/data");
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer del-token");
  });

  it("sends no Authorization when there is no token", async () => {
    mocks.getIdToken.mockResolvedValue(null);
    const fetchMock = mockFetch(200, { deleted: 0 });
    vi.stubGlobal("fetch", fetchMock);
    await cinemoryApi.deleteMyData();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    // No `headers` key is added by the caller, so only request()'s default
    // remains and no Authorization is ever sent.
    expect(init.headers).toEqual({ Accept: "application/json" });
    expect(init.method).toBe("DELETE");
  });
});
