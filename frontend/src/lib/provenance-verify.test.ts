import { describe, expect, it, vi } from "vitest";
import {
  parseJsonPreservingLexemes,
  pythonCanonicalJson,
  pythonEscapeString,
  sha256HexUtf8,
  verifyManifestText,
  verifyReelProvenance,
} from "./provenance-verify";
// The GOLDEN fixture is the raw HTTP body of `GET /reels/{name}` produced by
// the REAL backend (FastAPI TestClient over the offline pipeline) — see the
// fixture's sidecar .expected.json. It deliberately exercises non-ASCII
// (Greek + astral 🎬 in the reel name → ensure_ascii escaping) and integral
// float lexemes (tempo 88.0 → Python "88.0" vs JS "88").
import goldenRaw from "../test/fixtures/golden-manifest.json?raw";
import goldenExpected from "../test/fixtures/golden-manifest.expected.json";

describe("pythonEscapeString (json.dumps ensure_ascii=True parity)", () => {
  it("escapes non-ASCII as lowercase \\uXXXX", () => {
    expect(pythonEscapeString("μνήμη")).toBe("\\u03bc\\u03bd\\u03ae\\u03bc\\u03b7");
  });
  it("escapes astral characters as surrogate pairs (Python parity)", () => {
    expect(pythonEscapeString("🎬")).toBe("\\ud83c\\udfac");
  });
  it("uses the short escapes and escapes DEL like Python", () => {
    expect(pythonEscapeString('a"b\\c\nd\te')).toBe('a\\"b\\\\c\\nd\\te');
    expect(pythonEscapeString("\x7f")).toBe("\\u007f"); // Python escapes 0x7f too
    expect(pythonEscapeString("\x01")).toBe("\\u0001");
  });
});

describe("lexeme-preserving canonicalization", () => {
  it("preserves Python float lexemes that JSON.stringify would destroy", () => {
    const tree = parseJsonPreservingLexemes('{"b": 96.0, "a": 4, "c": 1e-05}');
    // JSON.stringify(JSON.parse(...)) would emit 96 — the hash would break.
    expect(pythonCanonicalJson(tree)).toBe('{"a":4,"b":96.0,"c":1e-05}');
  });

  it("sorts keys by code point and uses compact separators", () => {
    const tree = parseJsonPreservingLexemes('{"z": 1, "a": true, "m": null}');
    expect(pythonCanonicalJson(tree)).toBe('{"a":true,"m":null,"z":1}');
  });

  it("drops ONLY the top-level manifest_hash, never nested keys", () => {
    const tree = parseJsonPreservingLexemes(
      '{"manifest_hash": "x", "nested": {"manifest_hash": "keep"}}',
    );
    expect(pythonCanonicalJson(tree, "manifest_hash")).toBe(
      '{"nested":{"manifest_hash":"keep"}}',
    );
  });

  it("round-trips escaped input strings to Python-canonical escapes", () => {
    const tree = parseJsonPreservingLexemes('{"k": "καλή\\nμέρα"}');
    expect(pythonCanonicalJson(tree)).toBe(
      '{"k":"\\u03ba\\u03b1\\u03bb\\u03ae\\n\\u03bc\\u03ad\\u03c1\\u03b1"}',
    );
  });

  it("throws SyntaxError on malformed JSON", () => {
    expect(() => parseJsonPreservingLexemes('{"a": }')).toThrow(SyntaxError);
    expect(() => parseJsonPreservingLexemes('{"a": 1} trailing')).toThrow(SyntaxError);
  });
});

describe("sha256HexUtf8", () => {
  it("matches a known SHA-256 vector", async () => {
    // echo -n "abc" | sha256sum
    expect(await sha256HexUtf8("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("verifyManifestText against the GOLDEN backend fixture", () => {
  it("recomputes the exact manifest_hash sealed by the real backend", async () => {
    const outcome = await verifyManifestText(goldenRaw);
    expect(outcome.claimedHash).toBe(goldenExpected.manifest_hash);
    expect(outcome.computedHash).toBe(goldenExpected.manifest_hash);
    expect(outcome.verified).toBe(true);
  });

  it("detects tampering with any recorded field", async () => {
    // Flip one character inside a hashed field of the served body.
    const tampered = goldenRaw.replace('"occasion":"wedding"', '"occasion":"Wedding"');
    expect(tampered).not.toBe(goldenRaw);
    const outcome = await verifyManifestText(tampered);
    expect(outcome.verified).toBe(false);
    expect(outcome.computedHash).not.toBe(outcome.claimedHash);
  });
});

describe("verifyReelProvenance", () => {
  const golden = { hash: goldenExpected.manifest_hash };
  const okResponse = (text: string) =>
    ({ ok: true, status: 200, text: async () => text }) as Response;

  it("verifies a genuine manifest against the displayed hash", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(goldenRaw));
    const res = await verifyReelProvenance("golden", golden.hash, fetchImpl);
    expect(res.state).toBe("verified");
    expect(res.computedHash).toBe(golden.hash);
    expect(fetchImpl).toHaveBeenCalledWith(
      "/reels/golden",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("fails when the manifest bytes were tampered with", async () => {
    const tampered = goldenRaw.replace('"occasion":"wedding"', '"occasion":"Wedding"');
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(tampered));
    const res = await verifyReelProvenance("golden", golden.hash, fetchImpl);
    expect(res.state).toBe("failed");
    expect(res.detail).toMatch(/does not match/i);
  });

  it("fails when the re-fetched manifest doesn't match the hash on screen", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(goldenRaw));
    const res = await verifyReelProvenance("golden", "f".repeat(64), fetchImpl);
    expect(res.state).toBe("failed");
    expect(res.detail).toMatch(/on screen/i);
  });

  it("is honest (unavailable, not failed) when the manifest can't be fetched", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 404, text: async () => "" } as Response);
    expect((await verifyReelProvenance("golden", golden.hash, fetchImpl)).state).toBe(
      "unavailable",
    );

    const netFail = vi.fn().mockRejectedValue(new TypeError("network down"));
    expect((await verifyReelProvenance("golden", golden.hash, netFail)).state).toBe(
      "unavailable",
    );
  });

  it("url-encodes reel names on the manifest fetch", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(okResponse(goldenRaw));
    await verifyReelProvenance("golden μ/../x", null, fetchImpl);
    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      "/reels/golden%20%CE%BC%2F..%2Fx",
    );
  });
});
