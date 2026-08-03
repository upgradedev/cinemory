import { describe, expect, it } from "vitest";
import { degradeCause, degradeNote, type DegradeKind } from "./degrade";

const KINDS: DegradeKind[] = [
  "credit",
  "busy",
  "timeout",
  "unavailable",
  "refused",
  "unknown",
];

describe("degradeCause", () => {
  it("gives every category its own plain sentence", () => {
    const sentences = KINDS.map((k) => degradeCause(k));
    expect(new Set(sentences).size).toBe(KINDS.length);
    for (const s of sentences) expect(s).toMatch(/\.$/);
  });

  it("names the billing case specifically, which is the one that started this", () => {
    expect(degradeCause("credit")).toMatch(/credit ran out/i);
  });

  it("falls back to the honest general sentence for anything it does not know", () => {
    // An older backend sends no category at all; a newer one may send a
    // category this build has never heard of. Neither may render a blank.
    for (const unknown of [undefined, null, "", "sunspots", "402"]) {
      expect(degradeCause(unknown)).toBe(degradeCause("unknown"));
    }
  });
});

describe("degradeNote", () => {
  it("says the cause AND what it means for the reel in hand", () => {
    const note = degradeNote("credit");
    expect(note).toContain(degradeCause("credit"));
    expect(note).toMatch(/built-in fallback/i);
    expect(note).toMatch(/labelled as such/i);
    expect(note).toMatch(/storage and provenance are real/i);
  });

  it("never leaks provider internals, credentials or an upstream message", () => {
    // The category is the ONLY thing that crosses the wire; everything the
    // exception actually said stays in the server log. This pins that: no
    // provider or cloud name, no status code, no exception class name.
    for (const kind of [...KINDS, "402", "GMICloud submit failed (402)"]) {
      const note = degradeNote(kind);
      expect(note).not.toMatch(/GMI|genblaze|kling|seedance|bearer|token|api[_ -]?key/i);
      expect(note).not.toMatch(/\b[45]\d{2}\b/);
      expect(note).not.toMatch(/Error\b/);
      expect(note).not.toMatch(/—/);
    }
  });
});
