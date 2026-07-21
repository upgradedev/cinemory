import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, cinemoryApi } from "./api";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("cinemoryApi.occasions", () => {
  it("parses and unwraps the occasions array", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(200, {
        occasions: [
          {
            key: "anniversary",
            label: "Anniversary",
            music_style: "warm strings",
            tempo: 96,
            seconds_per_clip: 3.5,
            transition: "cross-dissolve",
            title_style: "serif",
            aspect_ratio: "16:9",
          },
        ],
      }),
    );
    const occ = await cinemoryApi.occasions();
    expect(occ).toHaveLength(1);
    expect(occ[0]?.key).toBe("anniversary");
  });

  it("throws ApiError on a malformed shape", async () => {
    vi.stubGlobal("fetch", mockFetch(200, { occasions: [{ key: 123 }] }));
    await expect(cinemoryApi.occasions()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("cinemoryApi.createReel", () => {
  it("validates the reel response", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(200, {
        reel_name: "demo",
        occasion: "wedding",
        reel_url: "b2://bucket/demo.mp4",
        reel_sha256: "abc",
        manifest_uri: "b2://bucket/m.json",
        manifest_hash: "def",
        steps: 6,
      }),
    );
    const r = await cinemoryApi.createReel({
      name: "demo",
      occasion: "wedding",
      chapters: 3,
      per_chapter: 2,
    });
    expect(r.steps).toBe(6);
    expect(r.reel_url).toBe("b2://bucket/demo.mp4");
  });

  it("keeps playback_url and the honest provider/degrade fields", async () => {
    // These fields drive the player URL and the degrade badge — the schema must
    // carry them through, not strip them (the old schema silently dropped them).
    vi.stubGlobal(
      "fetch",
      mockFetch(200, {
        reel_name: "demo",
        occasion: "wedding",
        reel_url: "https://bucket.s3.example/demo/reels/ab/cd/reel.mp4",
        playback_url: "/reels/demo/video",
        reel_sha256: "abc",
        manifest_uri: "b2://bucket/m.json",
        manifest_hash: "def",
        steps: 6,
        provider: "fake-genblaze",
        provider_degraded: true,
        degrade_reason: "RuntimeError",
      }),
    );
    const r = await cinemoryApi.createReel({
      name: "demo",
      occasion: "wedding",
      chapters: 3,
      per_chapter: 2,
    });
    expect(r.playback_url).toBe("/reels/demo/video");
    expect(r.provider).toBe("fake-genblaze");
    expect(r.provider_degraded).toBe(true);
    expect(r.degrade_reason).toBe("RuntimeError");
  });

  it("still parses responses from older backends without the new fields", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch(200, {
        reel_name: "old",
        reel_url: null,
        reel_sha256: "abc",
        manifest_uri: null,
        manifest_hash: "def",
        steps: 2,
      }),
    );
    const r = await cinemoryApi.createReel({
      name: "old",
      occasion: "wedding",
      chapters: 1,
      per_chapter: 2,
    });
    expect(r.playback_url).toBeUndefined();
    expect(r.provider_degraded).toBeUndefined();
  });
});

describe("cinemoryApi.uploadReel", () => {
  it("posts real files as multipart/form-data and parses the reel", async () => {
    const fetchMock = mockFetch(200, {
      reel_name: "cinemory-reel",
      occasion: "wedding",
      reel_url: "b2://bucket/r.mp4",
      reel_sha256: "abc",
      manifest_uri: "b2://bucket/m.json",
      manifest_hash: "def",
      steps: 5,
    });
    vi.stubGlobal("fetch", fetchMock);

    const file = new File([new Uint8Array([1, 2, 3])], "memory.png", {
      type: "image/png",
    });
    const r = await cinemoryApi.uploadReel({
      name: "cinemory-reel",
      occasion: "wedding",
      chapters: 3,
      files: [file],
    });
    expect(r.steps).toBe(5);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/reels/upload-multipart");
    expect(init.method).toBe("POST");
    // Must be FormData (browser sets the multipart boundary) — never a JSON body
    // and never a caller-set Content-Type that would clobber the boundary.
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    const body = init.body as FormData;
    expect(body.getAll("files")).toHaveLength(1);
    expect(body.get("occasion")).toBe("wedding");
    expect(body.get("chapters")).toBe("3");
  });

  it("surfaces a 5xx as ApiError, not a silent failure", async () => {
    vi.stubGlobal("fetch", mockFetch(500, { detail: "boom" }));
    await expect(
      cinemoryApi.uploadReel({
        name: "x",
        occasion: "wedding",
        chapters: 3,
        files: [],
      }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("cinemoryApi.manifest", () => {
  it("returns null on 404 (live path)", async () => {
    vi.stubGlobal("fetch", mockFetch(404, { detail: "nope" }));
    await expect(cinemoryApi.manifest("x")).resolves.toBeNull();
  });

  it("surfaces network failures as ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    await expect(cinemoryApi.health()).rejects.toBeInstanceOf(ApiError);
  });
});
