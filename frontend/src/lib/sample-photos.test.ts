import { describe, expect, it } from "vitest";
import {
  SAMPLE_PHOTO_COUNT,
  generateSamplePhotos,
  mulberry32,
  samplePhotoAlts,
  samplePhotoSpecs,
} from "./sample-photos";
import { MAX_REEL_PHOTOS } from "./reel-budget";

describe("samplePhotoSpecs", () => {
  it("is deterministic: identical storyboard on every call", () => {
    expect(samplePhotoSpecs()).toEqual(samplePhotoSpecs());
  });

  it("ships exactly one full reel of honestly-labelled, uniquely-named frames", () => {
    const specs = samplePhotoSpecs();
    expect(specs).toHaveLength(SAMPLE_PHOTO_COUNT);
    // The demo path exists to FINISH. Handing over more photos than one reel
    // can hold would trip the "some were left out" notice on the very path
    // built to be frictionless, so the sample set is exactly a full reel.
    expect(SAMPLE_PHOTO_COUNT).toBe(MAX_REEL_PHOTOS);
    specs.forEach((s, i) => {
      expect(s.label).toBe(`Sample ${i + 1}`);
      expect(s.filename).toMatch(/^cinemory-sample-\d+\.png$/);
    });
    expect(new Set(specs.map((s) => s.filename)).size).toBe(specs.length);
    expect(new Set(specs.map((s) => s.seed)).size).toBe(specs.length);
  });
});

describe("samplePhotoAlts", () => {
  it("gives every frame descriptive alt text aligned to the specs — never the filename", () => {
    const alts = samplePhotoAlts();
    const specs = samplePhotoSpecs();
    expect(alts).toHaveLength(specs.length);
    alts.forEach((alt, i) => {
      expect(alt).toBe(specs[i]!.description);
      expect(alt.length).toBeGreaterThan(12); // a real phrase, not a slug
      expect(alt).not.toMatch(/\.png$/i); // never the filename
    });
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
