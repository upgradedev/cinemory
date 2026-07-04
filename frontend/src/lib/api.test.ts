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
