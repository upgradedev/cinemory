import { describe, expect, it } from "vitest";
import {
  LIVE_SECONDS_PER_PHOTO,
  MAX_REEL_PHOTOS,
  REEL_JOB_MAX_POLL_MS,
  RUN_OVERHEAD_SECONDS,
  estimateSentence,
  estimatedRenderLabel,
  estimatedRenderSeconds,
  photoCountLabel,
} from "./reel-budget";

describe("MAX_REEL_PHOTOS", () => {
  it("is DERIVED from the budget, not typed in", () => {
    // The whole point of the cap: every photo that fits must actually finish
    // inside the window the app is willing to wait. This is the arithmetic
    // itself, so it fails the moment the ceiling or the measurement moves
    // without the cap moving with it.
    const budget = REEL_JOB_MAX_POLL_MS / 1000 - RUN_OVERHEAD_SECONDS;
    expect(MAX_REEL_PHOTOS).toBe(Math.floor(budget / LIVE_SECONDS_PER_PHOTO));
  });

  it("holds at today's measured numbers: 720s budget, 314s per photo, 2 photos", () => {
    expect(REEL_JOB_MAX_POLL_MS).toBe(720_000);
    expect(LIVE_SECONDS_PER_PHOTO).toBe(314);
    expect(MAX_REEL_PHOTOS).toBe(2);
  });

  it("a full reel fits in the window and one more photo would not", () => {
    expect(estimatedRenderSeconds(MAX_REEL_PHOTOS)).toBeLessThan(
      REEL_JOB_MAX_POLL_MS / 1000,
    );
    const oneMore =
      (MAX_REEL_PHOTOS + 1) * LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS;
    expect(oneMore).toBeGreaterThan(REEL_JOB_MAX_POLL_MS / 1000);
  });
});

describe("estimatedRenderSeconds", () => {
  it("scales with the photo count, because generation is one call per photo", () => {
    expect(estimatedRenderSeconds(1)).toBe(LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS);
    expect(estimatedRenderSeconds(2)).toBe(2 * LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS);
  });

  it("never estimates less than one photo, or more than a reel can hold", () => {
    expect(estimatedRenderSeconds(0)).toBe(estimatedRenderSeconds(1));
    expect(estimatedRenderSeconds(-4)).toBe(estimatedRenderSeconds(1));
    expect(estimatedRenderSeconds(99)).toBe(estimatedRenderSeconds(MAX_REEL_PHOTOS));
  });
});

describe("estimatedRenderLabel", () => {
  it("says the wait in whole minutes", () => {
    expect(estimatedRenderLabel(1)).toBe("about 6 minutes"); // 359s
    expect(estimatedRenderLabel(2)).toBe("about 11 minutes"); // 673s
  });

  it("never says 'about 0 minutes'", () => {
    expect(estimatedRenderLabel(1)).not.toMatch(/\b0 minutes\b/);
  });
});

describe("photoCountLabel", () => {
  it("agrees in number", () => {
    expect(photoCountLabel(1)).toBe("1 photo");
    expect(photoCountLabel(2)).toBe("2 photos");
    expect(photoCountLabel(0)).toBe("0 photos");
  });
});

describe("estimateSentence", () => {
  it("is a whole sentence whose verb agrees with the count", () => {
    expect(estimateSentence(1)).toBe("1 photo usually takes about 6 minutes.");
    expect(estimateSentence(2)).toBe("2 photos usually take about 11 minutes.");
  });

  it("stays free of developer vocabulary and em-dashes", () => {
    for (const n of [1, 2]) {
      const sentence = estimateSentence(n);
      expect(sentence).not.toMatch(/—/);
      expect(sentence).not.toMatch(/\b(job|poll|API|render|queue)\b/i);
    }
  });
});
