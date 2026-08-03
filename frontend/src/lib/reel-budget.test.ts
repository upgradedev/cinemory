import { describe, expect, it } from "vitest";
import {
  LIVE_SECONDS_PER_PHOTO,
  MAX_CONCURRENT_GENERATIONS,
  MAX_REEL_PHOTOS,
  REEL_JOB_MAX_POLL_MS,
  RUN_OVERHEAD_SECONDS,
  capFitsTheWindow,
  estimateSentence,
  estimatedRenderLabel,
  estimatedRenderSeconds,
  photoCountLabel,
  renderWaves,
} from "./reel-budget";

describe("MAX_REEL_PHOTOS", () => {
  it("is 5, and a full reel still finishes inside the window", () => {
    expect(MAX_REEL_PHOTOS).toBe(5);
    expect(capFitsTheWindow()).toBe(true);
    // The whole point of checking rather than deriving: if someone raises the
    // cap, drops the concurrency, or the measurement gets worse, this fails
    // instead of a visitor finding out by waiting.
    expect(estimatedRenderSeconds(MAX_REEL_PHOTOS)).toBeLessThan(
      REEL_JOB_MAX_POLL_MS / 1000,
    );
  });

  it("holds at today's measured numbers", () => {
    expect(REEL_JOB_MAX_POLL_MS).toBe(720_000);
    expect(LIVE_SECONDS_PER_PHOTO).toBe(314);
    expect(RUN_OVERHEAD_SECONDS).toBe(45);
    expect(MAX_CONCURRENT_GENERATIONS).toBe(5);
  });

  it("could not have held 5 photos sequentially, which is why concurrency exists", () => {
    const sequential = MAX_REEL_PHOTOS * LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS;
    expect(sequential).toBeGreaterThan(REEL_JOB_MAX_POLL_MS / 1000);
    // One wave instead of five: 359s against 1615s.
    expect(estimatedRenderSeconds(MAX_REEL_PHOTOS)).toBe(
      LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS,
    );
  });
});

describe("renderWaves", () => {
  it("packs photos into concurrent waves", () => {
    expect(renderWaves(1)).toBe(1);
    expect(renderWaves(MAX_CONCURRENT_GENERATIONS)).toBe(1);
    expect(renderWaves(MAX_CONCURRENT_GENERATIONS + 1)).toBe(2);
    // Never zero waves, however odd the count.
    expect(renderWaves(0)).toBe(1);
    expect(renderWaves(-3)).toBe(1);
  });
});

describe("estimatedRenderSeconds", () => {
  it("costs one wave, not one photo at a time", () => {
    // Every count up to the cap is a single wave, so the estimate is flat.
    for (let n = 1; n <= MAX_REEL_PHOTOS; n += 1) {
      expect(estimatedRenderSeconds(n)).toBe(
        LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS,
      );
    }
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
    expect(estimatedRenderLabel(5)).toBe("about 6 minutes"); // same wave
  });

  it("never says 'about 0 minutes'", () => {
    expect(estimatedRenderLabel(1)).not.toMatch(/0 minutes/);
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
    expect(estimateSentence(5)).toBe("5 photos usually take about 6 minutes.");
  });

  it("stays free of developer vocabulary and em-dashes", () => {
    for (let n = 1; n <= MAX_REEL_PHOTOS; n += 1) {
      const sentence = estimateSentence(n);
      expect(sentence).not.toMatch(/—/);
      expect(sentence).not.toMatch(/(job|poll|API|render|queue)/i);
    }
  });
});
