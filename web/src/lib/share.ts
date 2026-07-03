// Web Share API share-sheet + export helpers for a generated reel.
//
// The native share sheet (navigator.share with files) reaches Instagram,
// Facebook, LinkedIn, YouTube and every other installed target with ZERO
// platform API review. A download button and per-platform deep-links are the
// graceful fallback where the Web Share API (or file sharing) is unavailable
// — e.g. most desktop browsers.
//
// Every function is dependency-injectable (navigator / document) so the pure
// logic is testable and the DOM-touching paths stay thin.

export interface ShareMeta {
  title: string;
  text: string;
  /** Canonical, publicly reachable page/reel URL for share + deep-links. */
  pageUrl: string;
}

export interface PlatformLinks {
  instagram: string;
  facebook: string;
  linkedin: string;
  youtube: string;
}

/**
 * Per-platform deep-links for a reel's public page URL. Pure function.
 *
 * Facebook and LinkedIn expose share-by-URL endpoints. Instagram and YouTube
 * have no web share-by-URL API, so we deep-link to the app / Studio where the
 * user attaches the reel they just downloaded — the same pattern every
 * consumer video tool uses.
 */
export function platformDeepLinks(pageUrl: string): PlatformLinks {
  const u = encodeURIComponent(pageUrl);
  return {
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
    instagram: "https://www.instagram.com/",
    youtube: "https://studio.youtube.com/",
  };
}

/** A filesystem-safe download filename for a reel. Pure function. */
export function reelFilename(reelName: string): string {
  const slug = reelName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "reel"}.mp4`;
}

/** Whether the environment can share these files via the Web Share API. Pure-ish. */
export function canShareFiles(files: File[], nav: Navigator = navigator): boolean {
  return (
    typeof nav.share === "function" &&
    typeof nav.canShare === "function" &&
    nav.canShare({ files })
  );
}

/** Fetch reel bytes from a public / pre-signed URL and wrap them as a File. */
export async function fetchReelFile(url: string, filename: string): Promise<File> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`reel fetch failed: ${res.status}`);
  const blob = await res.blob();
  return new File([blob], filename, { type: blob.type || "video/mp4" });
}

export type ShareOutcome = "shared" | "unsupported" | "cancelled";

/** Open the native share sheet with the reel file attached. */
export async function shareReel(
  file: File,
  meta: ShareMeta,
  nav: Navigator = navigator,
): Promise<ShareOutcome> {
  if (!canShareFiles([file], nav)) return "unsupported";
  try {
    await nav.share({ files: [file], title: meta.title, text: meta.text, url: meta.pageUrl });
    return "shared";
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return "cancelled";
    throw err;
  }
}

/** Trigger a browser download of the reel (share-sheet fallback / export). */
export function downloadReel(file: Blob, filename: string, doc: Document = document): void {
  const url = URL.createObjectURL(file);
  const a = doc.createElement("a");
  a.href = url;
  a.download = filename;
  doc.body.appendChild(a);
  a.click();
  doc.body.removeChild(a);
  URL.revokeObjectURL(url);
}
