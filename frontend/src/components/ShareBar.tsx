import { useState } from "react";
import { Download, Facebook, Instagram, Linkedin, Share2, Youtube } from "lucide-react";
import { Button } from "./ui/button";
import type { ReelResponse } from "@/lib/api";
import { isPlayableUrl } from "@/lib/utils";
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

  const fetchable = isPlayableUrl(reel.reel_url);
  const filename = reelFilename(reel.reel_name);
  const pageUrl =
    reel.reel_url ?? (typeof location !== "undefined" ? location.href : "");
  const links = platformDeepLinks(pageUrl);

  const onShare = async () => {
    if (!reel.reel_url) return;
    setBusy(true);
    try {
      const file = await fetchReelFile(reel.reel_url, filename);
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
    if (!reel.reel_url) return;
    setBusy(true);
    try {
      const file = await fetchReelFile(reel.reel_url, filename);
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
          Offline demo: the reel is stored at{" "}
          <span className="font-mono text-zinc-400">{reel.reel_url ?? "(none)"}</span>.
          Share &amp; Download activate on the live Backblaze B2 path (public HTTPS URL).
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
