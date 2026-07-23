import { describe, expect, it } from "vitest";
import { SAMPLE_PHOTO_COUNT, generateSamplePhotos } from "./sample-photos";

// jsdom ships no canvas backend, so getContext("2d") is null there and the
// drawing code (every scene branch + the gradient/ridge/vignette/label
// helpers) never runs. We inject a faithful no-op 2D context so the full
// paint path executes for all five scenes and returns real File objects.
function fakeGradient() {
  return { addColorStop: () => {} };
}

function fakeCtx(): CanvasRenderingContext2D {
  return {
    createLinearGradient: () => fakeGradient(),
    createRadialGradient: () => fakeGradient(),
    fillRect: () => {},
    beginPath: () => {},
    arc: () => {},
    fill: () => {},
    moveTo: () => {},
    lineTo: () => {},
    closePath: () => {},
    roundRect: () => {},
    fillText: () => {},
    measureText: (t: string) => ({ width: t.length * 8 }),
    fillStyle: "",
    font: "",
    textBaseline: "",
  } as unknown as CanvasRenderingContext2D;
}

function fakeDoc(toBlobResult: Blob | null): Document {
  return {
    createElement: () =>
      ({
        width: 0,
        height: 0,
        getContext: () => fakeCtx(),
        toBlob: (cb: (b: Blob | null) => void) => cb(toBlobResult),
      }) as unknown as HTMLCanvasElement,
  } as unknown as Document;
}

describe("generateSamplePhotos — full paint path", () => {
  it("paints every scene and returns real, named PNG File objects", async () => {
    const files = await generateSamplePhotos(
      fakeDoc(new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" })),
    );
    expect(files).toHaveLength(SAMPLE_PHOTO_COUNT);
    files.forEach((f, i) => {
      expect(f).toBeInstanceOf(File);
      expect(f.name).toBe(`cinemory-sample-${i + 1}.png`);
      expect(f.type).toBe("image/png");
    });
  });

  it("rejects when the canvas cannot encode a PNG (toBlob yields null)", async () => {
    await expect(generateSamplePhotos(fakeDoc(null))).rejects.toThrow(
      /could not encode/i,
    );
  });
});
