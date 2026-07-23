import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deriveReelShape, useReelStore } from "./useReelStore";

function imageFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "image/png" });
}

beforeEach(() => {
  useReelStore.getState().reset();
});

afterEach(() => vi.restoreAllMocks());

describe("useReelStore — photos", () => {
  it("adds only image files, wrapping each as a LocalPhoto with a preview url", () => {
    useReelStore.getState().addPhotos([
      imageFile("a.png"),
      new File(["x"], "notes.txt", { type: "text/plain" }), // filtered out
      imageFile("b.png"),
    ]);
    const { photos } = useReelStore.getState();
    expect(photos).toHaveLength(2);
    expect(photos.map((p) => p.name)).toEqual(["a.png", "b.png"]);
    expect(photos[0]?.url).toBe("blob:mock");
    expect(photos[0]?.id).not.toBe(photos[1]?.id); // unique ids
  });

  it("removes a photo by id and revokes its object url", () => {
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    useReelStore.getState().addPhotos([imageFile("a.png"), imageFile("b.png")]);
    const target = useReelStore.getState().photos[0]!;
    useReelStore.getState().removePhoto(target.id);
    expect(useReelStore.getState().photos).toHaveLength(1);
    expect(useReelStore.getState().photos[0]?.name).toBe("b.png");
    expect(revoke).toHaveBeenCalledWith(target.url);
  });

  it("removePhoto is a no-op for an unknown id", () => {
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    useReelStore.getState().removePhoto("does-not-exist");
    expect(useReelStore.getState().photos).toHaveLength(1);
  });

  it("clearPhotos empties the set and revokes every url", () => {
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    useReelStore.getState().addPhotos([imageFile("a.png"), imageFile("b.png")]);
    useReelStore.getState().clearPhotos();
    expect(useReelStore.getState().photos).toHaveLength(0);
    expect(revoke).toHaveBeenCalledTimes(2);
  });
});

describe("useReelStore — reorderPhotos", () => {
  it("moves a photo from one position to another", () => {
    useReelStore
      .getState()
      .addPhotos([imageFile("a.png"), imageFile("b.png"), imageFile("c.png")]);
    const { photos } = useReelStore.getState();
    const firstId = photos[0]!.id;
    const lastId = photos[2]!.id;
    useReelStore.getState().reorderPhotos(firstId, lastId);
    expect(useReelStore.getState().photos.map((p) => p.name)).toEqual([
      "b.png",
      "c.png",
      "a.png",
    ]);
  });

  it("is a no-op when an id is unknown or source === target", () => {
    useReelStore.getState().addPhotos([imageFile("a.png"), imageFile("b.png")]);
    const before = useReelStore.getState().photos.map((p) => p.name);
    useReelStore.getState().reorderPhotos("missing", before[0]!);
    const same = useReelStore.getState().photos[0]!.id;
    useReelStore.getState().reorderPhotos(same, same);
    expect(useReelStore.getState().photos.map((p) => p.name)).toEqual(before);
  });
});

describe("useReelStore — navigation & reset", () => {
  it("sets the step, occasion and clears everything on reset", () => {
    useReelStore.getState().goTo("occasion");
    useReelStore.getState().setOccasion("wedding");
    useReelStore.getState().addPhotos([imageFile("a.png")]);
    expect(useReelStore.getState().step).toBe("occasion");
    expect(useReelStore.getState().occasionKey).toBe("wedding");

    const revoke = vi.spyOn(URL, "revokeObjectURL");
    useReelStore.getState().reset();
    expect(useReelStore.getState()).toMatchObject({
      step: "upload",
      photos: [],
      occasionKey: null,
    });
    expect(revoke).toHaveBeenCalledTimes(1);
  });
});

describe("deriveReelShape", () => {
  it("clamps chapters to 2..5 and per_chapter to 1..4", () => {
    expect(deriveReelShape(0)).toEqual({ chapters: 2, per_chapter: 1 });
    expect(deriveReelShape(1)).toEqual({ chapters: 2, per_chapter: 1 });
    expect(deriveReelShape(4)).toEqual({ chapters: 2, per_chapter: 2 });
    expect(deriveReelShape(9)).toEqual({ chapters: 3, per_chapter: 3 });
    // A large set saturates both clamps (chapters=5, per_chapter capped at 4).
    expect(deriveReelShape(100)).toEqual({ chapters: 5, per_chapter: 4 });
  });
});
