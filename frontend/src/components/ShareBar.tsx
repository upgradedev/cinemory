import { useEffect, useRef, useState } from "react";
import { Check, Download, Facebook, Link2, Linkedin, Share2 } from "lucide-react";
import { Button } from "./ui/button";
import type { ReelResponse } from "@/lib/api";
import { reelPlaybackUrl } from "@/lib/utils";
import {
  copyText,
  downloadReel,
  fetchReelFile,
  platformDeepLinks,
  reelFilename,
  shareReel,
} from "@/lib/share";

const PLATFORMS = [
  { key: "facebook", label: "Facebook", Icon: Facebook },
  { key: "linkedin", label: "LinkedIn", Icon: Linkedin },
] as const;

const PILL_CLASS =
  "inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-ink-900/60 px-3.5 py-1.5 text-xs text-zinc-300 transition-colors hover:border-gold-400/40 hover:text-gold-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-400/80";

export function ShareBar({ reel }: { reel: ReelResponse }) {
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (copiedTimer.current !== null) window.clearTimeout(copiedTimer.current);
    },
    [],
  );

  // Download/share fetch the stable api-relative playback route (fresh
  // presigned URL live, streamed bytes offline) — never the raw storage URL,
  // which is private and would 401. Null when the run isn't decodable video.
  const playbackUrl = reelPlaybackUrl(reel);
  const fetchable = playbackUrl !== null;
  const filename = reelFilename(reel.reel_name);
  // Deep links + Copy link share the app page, not a storage URL (which is
  // either private or a non-HTTP b2:// URI — neither is a link anyone can open).
  const pageUrl = typeof location !== "undefined" ? location.href : "";
  const links = platformDeepLinks(pageUrl);

  const onShare = async () => {
    if (!playbackUrl) return;
    setBusy(true);
    try {
      const file = await fetchReelFile(playbackUrl, filename);
      const outcome = await shareReel(file, {
        title: `Cinemory — ${reel.reel_name}`,
        text: "A cinematic memory reel, sealed with verifiable provenance.",
        pageUrl,
      });
      setStatus(
        outcome === "unsupported"
          ? "Native share isn’t available here — use Download or Copy link."
          : `Share ${outcome}.`,
      );
    } catch (e) {
      setStatus(`Share failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const onDownload = async () => {
    if (!playbackUrl) return;
    setBusy(true);
    try {
      const file = await fetchReelFile(playbackUrl, filename);
      downloadReel(file, filename);
    } catch (e) {
      setStatus(`Download failed: ${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  // Honest, always-works affordance (replaces the old Instagram/YouTube links,
  // which just opened their homepages): copy the app share URL, with visible
  // checkmark feedback + a polite screen-reader announcement.
  const onCopyLink = async () => {
    try {
      await copyText(pageUrl);
      setCopied(true);
      if (copiedTimer.current !== null) window.clearTimeout(copiedTimer.current);
      copiedTimer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setStatus("Copy failed — copy the address from the address bar instead.");
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        <Button onClick={onShare} disabled={!fetchable || busy}>
          <Share2 className="h-4 w-4" />
          Share
        </Button>
        <Button variant="secondary" onClick={onDownload} disabled={!fetchable || busy}>
          <Download className="h-4 w-4" />
          Download .mp4
        </Button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {PLATFORMS.map(({ key, label, Icon }) => (
          <a
            key={key}
            href={links[key]}
            target="_blank"
            rel="noopener noreferrer"
            className={PILL_CLASS}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </a>
        ))}
        <button type="button" onClick={onCopyLink} className={PILL_CLASS}>
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Link2 className="h-3.5 w-3.5" />
          )}
          {copied ? "Copied" : "Copy link"}
        </button>
        <span role="status" aria-live="polite" className="sr-only">
          {copied ? "Link copied to clipboard" : ""}
        </span>
      </div>

      {!fetchable && (
        <p className="mt-4 text-xs text-zinc-500">
          This run was rendered by the built-in offline generator, so there is no
          playable video to share yet — the reel is still stored and sealed at{" "}
          <span className="font-mono text-zinc-400">{reel.reel_url ?? "(none)"}</span>.
          Share &amp; Download activate on live AI-generated reels.
        </p>
      )}
      {status && (
        <p className="mt-3 text-xs text-zinc-400" role="status">
          {status}
        </p>
      )}
    </div>
  );
}
