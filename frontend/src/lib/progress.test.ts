import { describe, expect, it } from "vitest";
import {
  PENDING_CEIL_PCT,
  generationProgressPct,
  stagedFrontPct,
} from "./progress";

const TOTAL = 7; // the GenerateReel stage list length

describe("generationProgressPct", () => {
  it("returns 100 only when the response actually landed", () => {
    expect(
      generationProgressPct({ stage: 2, totalStages: TOTAL, tailElapsedMs: 0, done: true }),
    ).toBe(100);
    expect(
      generationProgressPct({
        stage: TOTAL - 1,
        totalStages: TOTAL,
        tailElapsedMs: Number.MAX_SAFE_INTEGER,
        done: false,
      }),
    ).toBe(PENDING_CEIL_PCT); // asymptote never fakes completion
  });

  it("keeps the honest staged front-load before the last stage", () => {
    for (let stage = 0; stage < TOTAL - 1; stage += 1) {
      expect(
        generationProgressPct({ stage, totalStages: TOTAL, tailElapsedMs: 0, done: false }),
      ).toBe(stagedFrontPct(stage, TOTAL));
    }
    expect(stagedFrontPct(TOTAL - 1, TOTAL)).toBe(86); // the old freeze point
  });

  it("keeps crawling monotonically through the tail instead of freezing at 86", () => {
    const at = (ms: number) =>
      generationProgressPct({
        stage: TOTAL - 1,
        totalStages: TOTAL,
        tailElapsedMs: ms,
        done: false,
      });
    const samples = [0, 1_000, 3_000, 6_000, 12_000, 30_000, 90_000].map(at);
    expect(samples[0]).toBe(86);
    for (let i = 1; i < samples.length; i += 1) {
      expect(samples[i]).toBeGreaterThanOrEqual(samples[i - 1] as number);
    }
    expect(at(12_000)).toBeGreaterThan(90); // visibly moving within one tau
    expect(at(90_000)).toBeLessThanOrEqual(PENDING_CEIL_PCT);
  });
});
