import { useState } from "react";
import { Download, Facebook, Instagram, Linkedin, Share2, Youtube } from "lucide-react";
import { Button } from "./ui/button";
import type { ReelResponse } from "@/lib/api";
import { reelPlaybackUrl } from "@/lib/utils";
import {
  downloadReel,
  fetchReelFile,
  platformDeepLinks,
  reelFilename,
  shareReel,
} from "@/lib/share";

const PLATFORMS = [
  { key: "facebook", label: "Facebook", Icon: Facebook },
  { key: "linkedin", label: "LinkedIn", Icon: Linkedin },
  { key: "instagram", label: "Instagram", Icon: Instagram },
  { key: "youtube", label: "YouTube", Icon: Youtube },
] as const;

export function ShareBar({ reel }: { reel: ReelResponse }) {
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);

  // Download/share fetch the stable api-relative playback route (fresh
  // presigned URL live, streamed bytes offline) — never the raw storage URL,
  // which is private and would 401. Null when the run isn't decodable video.
  const playbackUrl = reelPlaybackUrl(reel);
  const fetchable = playbackUrl !== null;
  const filename = reelFilename(reel.reel_name);
  // Deep links share the app page, not a storage URL (which is either private
  // or a non-HTTP b2:// URI — neither is a link anyone can open).
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
          ? "Native share isn’t available here — use Download or the platform links."
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
            className="inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-ink-900/60 px-3.5 py-1.5 text-xs text-zinc-300 transition-colors hover:border-gold-400/40 hover:text-gold-200"
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </a>
        ))}
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
