import { describe, expect, it } from "vitest";
import { formatBytes, isPlayableUrl, reelPlaybackUrl, shortHash } from "./utils";
import { reelFilename, platformDeepLinks } from "./share";
import { deriveReelShape } from "@/store/useReelStore";

describe("shortHash", () => {
  it("truncates long hashes with an ellipsis", () => {
    const h = "a".repeat(20) + "b".repeat(20);
    expect(shortHash(h)).toBe("aaaaaaaa…bbbbbbbb");
  });
  it("returns em dash for empty", () => {
    expect(shortHash(null)).toBe("—");
  });
  it("leaves short hashes intact", () => {
    expect(shortHash("abcd")).toBe("abcd");
  });
});

describe("formatBytes", () => {
  it("formats across units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
  it("handles nullish", () => {
    expect(formatBytes(null)).toBe("—");
  });
});

describe("isPlayableUrl", () => {
  it("accepts http(s), rejects b2:// and null", () => {
    expect(isPlayableUrl("https://x/y.mp4")).toBe(true);
    expect(isPlayableUrl("b2://bucket/key")).toBe(false);
    expect(isPlayableUrl(null)).toBe(false);
  });
});

describe("reelPlaybackUrl", () => {
  const base = {
    reel_url: "https://cinemory.s3.example/reel/ab/cd/reel.mp4" as string | null,
    playback_url: "/reels/demo/video",
    provider: "genblaze",
    provider_degraded: false,
  };

  it("prefers the stable api-relative playback route on a live generation", () => {
    expect(reelPlaybackUrl(base)).toBe("/reels/demo/video");
  });

  it("returns null when the run degraded to the offline generator", () => {
    // The degraded reel's bytes are sealed artifacts but not decodable video —
    // never hand them to <video> or the download/share fetch.
    expect(reelPlaybackUrl({ ...base, provider_degraded: true })).toBeNull();
  });

  it("returns null for the offline provider (offline demo mode)", () => {
    expect(reelPlaybackUrl({ ...base, provider: "fake-genblaze" })).toBeNull();
  });

  it("falls back to a fetchable storage URL for legacy backends", () => {
    // Old backend: no playback_url, no provider fields — keep prior behavior.
    expect(reelPlaybackUrl({ reel_url: "https://x/y.mp4" })).toBe("https://x/y.mp4");
    expect(reelPlaybackUrl({ reel_url: "b2://bucket/key" })).toBeNull();
    expect(reelPlaybackUrl({ reel_url: null })).toBeNull();
  });
});

describe("reelFilename", () => {
  it("slugifies to a safe .mp4 name", () => {
    expect(reelFilename("Our Anniversary 2026!")).toBe("our-anniversary-2026.mp4");
    expect(reelFilename("   ")).toBe("reel.mp4");
  });
});

describe("platformDeepLinks", () => {
  it("url-encodes the page url for share-by-url platforms", () => {
    const l = platformDeepLinks("https://cinemory.ai/r/abc");
    expect(l.facebook).toContain(encodeURIComponent("https://cinemory.ai/r/abc"));
    expect(l.linkedin).toContain("share-offsite");
  });

  it("offers ONLY platforms with a real share-by-url endpoint", () => {
    // Instagram/YouTube have none — their old entries were dead homepage
    // links, now replaced by the Copy-link affordance in the ShareBar.
    const l = platformDeepLinks("https://cinemory.ai/r/abc");
    expect(Object.keys(l).sort()).toEqual(["facebook", "linkedin"]);
  });
});

describe("deriveReelShape", () => {
  it("scales chapters with photo count and stays bounded", () => {
    expect(deriveReelShape(1).chapters).toBeGreaterThanOrEqual(2);
    const big = deriveReelShape(50);
    expect(big.chapters).toBeLessThanOrEqual(5);
    expect(big.per_chapter).toBeLessThanOrEqual(4);
  });
  it("covers every photo", () => {
    for (const n of [1, 4, 9, 12, 20]) {
      const { chapters, per_chapter } = deriveReelShape(n);
      expect(chapters * per_chapter).toBeGreaterThanOrEqual(n);
    }
  });
});
