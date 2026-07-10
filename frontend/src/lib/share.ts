// Web Share API + export helpers for a finished reel. Ported from the original
// web client so the full share feature set is preserved: native share sheet
// (reaches Instagram/Facebook/LinkedIn/YouTube with no platform review),
// download fallback, and per-platform deep-links.

export interface ShareMeta {
  title: string;
  text: string;
  pageUrl: string;
}

export interface PlatformLinks {
  facebook: string;
  linkedin: string;
  instagram: string;
  youtube: string;
}

export function platformDeepLinks(pageUrl: string): PlatformLinks {
  const u = encodeURIComponent(pageUrl);
  return {
    facebook: `https://www.facebook.com/sharer/sharer.php?u=${u}`,
    linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
    instagram: "https://www.instagram.com/",
    youtube: "https://studio.youtube.com/",
  };
}

export function reelFilename(reelName: string): string {
  const slug = reelName
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${slug || "reel"}.mp4`;
}

export function canShareFiles(files: File[], nav: Navigator = navigator): boolean {
  return (
    typeof nav.share === "function" &&
    typeof nav.canShare === "function" &&
    nav.canShare({ files })
  );
}

export async function fetchReelFile(url: string, filename: string): Promise<File> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Reel fetch failed (${res.status}).`);
  const blob = await res.blob();
  return new File([blob], filename, { type: blob.type || "video/mp4" });
}

export type ShareOutcome = "shared" | "unsupported" | "cancelled";

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

export function downloadReel(
  file: Blob,
  filename: string,
  doc: Document = document,
): void {
  const url = URL.createObjectURL(file);
  const a = doc.createElement("a");
  a.href = url;
  a.download = filename;
  doc.body.appendChild(a);
  a.click();
  doc.body.removeChild(a);
  URL.revokeObjectURL(url);
}
