import { afterEach, describe, expect, it } from "vitest";
import {
  REEL_HASH_PREFIX,
  forgetReel,
  parseHashRoute,
  reelHash,
  rememberReel,
} from "./hash-route";

afterEach(() => {
  window.history.replaceState(null, "", window.location.pathname);
});

describe("parseHashRoute", () => {
  it("reads no hash, an empty hash and an unrelated hash as no route", () => {
    // #main-content is the skip link's own target and must never be mistaken
    // for a route, or every keyboard visitor would land somewhere strange.
    for (const hash of ["", "#", "#main-content", "#pricing"]) {
      expect(parseHashRoute(hash)).toEqual({ kind: "none" });
    }
  });

  it("still reads the pre-existing #create deep link", () => {
    expect(parseHashRoute("#create")).toEqual({ kind: "create" });
  });

  it("reads a reel link as the reel it names", () => {
    // The real shape: secrets.token_urlsafe(18) server-side.
    const id = "PEYsghoylVNUrc2rNAdHJa6_";
    expect(parseHashRoute(`#reel/${id}`)).toEqual({ kind: "reel", jobId: id });
  });

  it("tolerates a hash handed over without its leading #", () => {
    expect(parseHashRoute("reel/abcdefghij")).toEqual({
      kind: "reel",
      jobId: "abcdefghij",
    });
  });

  it("decodes a percent-encoded id", () => {
    expect(parseHashRoute(`#reel/${encodeURIComponent("ab-cd_ef12")}`)).toEqual({
      kind: "reel",
      jobId: "ab-cd_ef12",
    });
  });

  it("calls out an id that cannot be real, rather than asking the server", () => {
    // Empty, too short, wrong alphabet, a traversal attempt, and a stray "%"
    // that makes decodeURIComponent itself throw. Every one of them has to
    // answer "broken", never throw and never resolve to a reel.
    for (const hash of [
      "#reel/",
      "#reel/ab",
      "#reel/not a job id",
      "#reel/../../etc/passwd",
      "#reel/%E0%A4%A",
      `#reel/${"x".repeat(200)}`,
    ]) {
      expect(parseHashRoute(hash), hash).toEqual({ kind: "broken" });
    }
  });
});

describe("reelHash", () => {
  it("builds the link shape the parser reads back", () => {
    const hash = reelHash("abcdefgh12");
    expect(hash).toBe(`${REEL_HASH_PREFIX}abcdefgh12`);
    expect(parseHashRoute(hash)).toEqual({ kind: "reel", jobId: "abcdefgh12" });
  });
});

describe("rememberReel / forgetReel", () => {
  it("puts the reel in the address bar WITHOUT adding a history entry", () => {
    // Back must still mean "leave this page", not "walk back through every
    // reel started in this tab", so this has to be a replace, not a push.
    const depthBefore = window.history.length;
    rememberReel("abcdefgh12");
    expect(window.location.hash).toBe("#reel/abcdefgh12");
    expect(window.history.length).toBe(depthBefore);
  });

  it("survives a round trip: what it writes is what parse reads", () => {
    rememberReel("PEYsghoylVNUrc2rNAdHJa6_");
    expect(parseHashRoute(window.location.hash)).toEqual({
      kind: "reel",
      jobId: "PEYsghoylVNUrc2rNAdHJa6_",
    });
  });

  it("clears the reel again so a refresh starts clean", () => {
    rememberReel("abcdefgh12");
    forgetReel();
    expect(window.location.hash).toBe("");
    expect(parseHashRoute(window.location.hash)).toEqual({ kind: "none" });
  });

  it("is a no-op when there is nothing to forget", () => {
    const before = window.location.href;
    forgetReel();
    expect(window.location.href).toBe(before);
  });
});
