import { describe, expect, it } from "vitest";
import {
  SAMPLE_PHOTO_COUNT,
  generateSamplePhotos,
  mulberry32,
  samplePhotoSpecs,
} from "./sample-photos";

describe("samplePhotoSpecs", () => {
  it("is deterministic: identical storyboard on every call", () => {
    expect(samplePhotoSpecs()).toEqual(samplePhotoSpecs());
  });

  it("ships 4–6 honestly-labelled, uniquely-named frames", () => {
    const specs = samplePhotoSpecs();
    expect(specs).toHaveLength(SAMPLE_PHOTO_COUNT);
    expect(SAMPLE_PHOTO_COUNT).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_PHOTO_COUNT).toBeLessThanOrEqual(6);
    specs.forEach((s, i) => {
      expect(s.label).toBe(`Sample ${i + 1}`);
      expect(s.filename).toMatch(/^cinemory-sample-\d+\.png$/);
    });
    expect(new Set(specs.map((s) => s.filename)).size).toBe(specs.length);
    expect(new Set(specs.map((s) => s.seed)).size).toBe(specs.length);
  });
});

describe("mulberry32", () => {
  it("is deterministic per seed and varies across seeds", () => {
    const a1 = mulberry32(42);
    const a2 = mulberry32(42);
    const b = mulberry32(43);
    const seqA1 = Array.from({ length: 5 }, a1);
    const seqA2 = Array.from({ length: 5 }, a2);
    const seqB = Array.from({ length: 5 }, b);
    expect(seqA1).toEqual(seqA2);
    expect(seqA1).not.toEqual(seqB);
    for (const v of seqA1) {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });
});

describe("generateSamplePhotos", () => {
  it("fails loudly (not silently) when Canvas 2D is unavailable", async () => {
    // jsdom has no canvas backend — getContext("2d") yields null. The
    // generator must surface that as a clear error the UI can show.
    const doc = {
      createElement: () =>
        ({ getContext: () => null }) as unknown as HTMLCanvasElement,
    } as unknown as Document;
    await expect(generateSamplePhotos(doc)).rejects.toThrow(/canvas 2d/i);
  });
});
