import { afterEach, describe, expect, it, vi } from "vitest";
import {
  canShareFiles,
  copyText,
  downloadReel,
  fetchReelFile,
  platformDeepLinks,
  reelFilename,
  shareReel,
  type ShareMeta,
} from "./share";

afterEach(() => vi.restoreAllMocks());

const meta: ShareMeta = {
  title: "Cinemory — demo",
  text: "A cinematic memory reel.",
  pageUrl: "https://cinemory.app/reel/demo",
};

function pngFile(name = "reel.mp4"): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: "video/mp4" });
}

describe("platformDeepLinks", () => {
  it("URL-encodes the page into the Facebook and LinkedIn sharers", () => {
    const links = platformDeepLinks("https://x.io/a b");
    expect(links.facebook).toContain("facebook.com/sharer/sharer.php?u=");
    expect(links.facebook).toContain(encodeURIComponent("https://x.io/a b"));
    expect(links.linkedin).toContain("share-offsite/?url=");
    expect(links.linkedin).toContain(encodeURIComponent("https://x.io/a b"));
  });
});

describe("reelFilename", () => {
  it("slugifies the reel name to a .mp4 filename", () => {
    expect(reelFilename("My Summer 2026!")).toBe("my-summer-2026.mp4");
  });

  it("falls back to reel.mp4 when the slug is empty", () => {
    expect(reelFilename("   ***   ")).toBe("reel.mp4");
  });
});

describe("copyText", () => {
  it("uses the async Clipboard API when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    await copyText("hello", { clipboard: { writeText } } as unknown as Navigator);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to a hidden textarea + execCommand when there is no clipboard", async () => {
    const execCommand = vi.fn().mockReturnValue(true);
    // A real document, but with execCommand shimmed (jsdom lacks it).
    (document as unknown as { execCommand: unknown }).execCommand = execCommand;
    const noClipboard = {} as unknown as Navigator;

    await copyText("copy me", noClipboard, document);
    expect(execCommand).toHaveBeenCalledWith("copy");
    // The temporary textarea is cleaned up afterwards.
    expect(document.querySelector("textarea")).toBeNull();
  });

  it("throws when the execCommand fallback reports failure", async () => {
    (document as unknown as { execCommand: unknown }).execCommand = vi
      .fn()
      .mockReturnValue(false);
    await expect(
      copyText("x", {} as unknown as Navigator, document),
    ).rejects.toThrow(/execCommand copy failed/i);
    // Even on failure the textarea must not leak into the DOM.
    expect(document.querySelector("textarea")).toBeNull();
  });
});

describe("canShareFiles", () => {
  it("is true only when share + canShare exist and accept the files", () => {
    const files = [pngFile()];
    expect(
      canShareFiles(files, {
        share: vi.fn(),
        canShare: vi.fn().mockReturnValue(true),
      } as unknown as Navigator),
    ).toBe(true);
    expect(
      canShareFiles(files, {
        share: vi.fn(),
        canShare: vi.fn().mockReturnValue(false),
      } as unknown as Navigator),
    ).toBe(false);
    // No Web Share API at all.
    expect(canShareFiles(files, {} as unknown as Navigator)).toBe(false);
  });
});

describe("fetchReelFile", () => {
  it("wraps a successful response body as a named File", async () => {
    const blob = new Blob([new Uint8Array([9, 9])], { type: "video/mp4" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, blob: async () => blob } as Response),
    );
    const file = await fetchReelFile("https://x/r.mp4", "out.mp4");
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe("out.mp4");
    expect(file.type).toBe("video/mp4");
    vi.unstubAllGlobals();
  });

  it("throws with the status code on a non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response),
    );
    await expect(fetchReelFile("https://x/r.mp4", "out.mp4")).rejects.toThrow(
      /503/,
    );
    vi.unstubAllGlobals();
  });
});

describe("shareReel", () => {
  it("returns 'unsupported' when the platform cannot share files", async () => {
    const outcome = await shareReel(pngFile(), meta, {} as unknown as Navigator);
    expect(outcome).toBe("unsupported");
  });

  it("returns 'shared' when the native share resolves", async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    const nav = {
      share,
      canShare: vi.fn().mockReturnValue(true),
    } as unknown as Navigator;
    expect(await shareReel(pngFile(), meta, nav)).toBe("shared");
    expect(share).toHaveBeenCalledOnce();
  });

  it("returns 'cancelled' when the user aborts the share sheet", async () => {
    const nav = {
      share: vi.fn().mockRejectedValue(new DOMException("no", "AbortError")),
      canShare: vi.fn().mockReturnValue(true),
    } as unknown as Navigator;
    expect(await shareReel(pngFile(), meta, nav)).toBe("cancelled");
  });

  it("re-throws non-abort share errors", async () => {
    const nav = {
      share: vi.fn().mockRejectedValue(new Error("boom")),
      canShare: vi.fn().mockReturnValue(true),
    } as unknown as Navigator;
    await expect(shareReel(pngFile(), meta, nav)).rejects.toThrow(/boom/);
  });
});

describe("downloadReel", () => {
  it("clicks a synthesized anchor and cleans up the object url", () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:dl");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.fn();
    const anchor = { href: "", download: "", click } as unknown as HTMLAnchorElement;
    const doc = {
      createElement: vi.fn().mockReturnValue(anchor),
      body: { appendChild: vi.fn(), removeChild: vi.fn() },
    } as unknown as Document;

    downloadReel(new Blob(["x"]), "memory.mp4", doc);

    expect(anchor.href).toBe("blob:dl");
    expect(anchor.download).toBe("memory.mp4");
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:dl");
    vi.unstubAllGlobals();
  });
});
