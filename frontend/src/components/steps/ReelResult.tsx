import { motion } from "framer-motion";
import { Clapperboard, PartyPopper, PlayCircle, RotateCcw } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { ProvenancePanel } from "../ProvenancePanel";
import { ShareBar } from "../ShareBar";
import { useOccasions } from "@/lib/queries";
import { useReelStore } from "@/store/useReelStore";
import { occasionTheme } from "@/lib/occasion-theme";
import { reelPlaybackUrl } from "@/lib/utils";
import type { ReelResponse } from "@/lib/api";

const DEGRADE_NOTE =
  "Live AI generation was unavailable for this run; storage and provenance are real.";

export function ReelResult({ reel }: { reel: ReelResponse }) {
  const photos = useReelStore((s) => s.photos);
  const reset = useReelStore((s) => s.reset);
  const { data: occasions } = useOccasions();

  const occasion = occasions?.find((o) => o.key === reel.occasion);
  const theme = occasionTheme(reel.occasion ?? "");
  const playbackUrl = reelPlaybackUrl(reel);
  const degraded = reel.provider_degraded === true;

  return (
    <div className="animate-fade-up">
      <div className="mb-8 text-center">
        <motion.span
          initial={{ scale: 0, rotate: -20 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 200, damping: 12 }}
          className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-gold-400/15 text-gold-300"
        >
          <PartyPopper className="h-7 w-7" />
        </motion.span>
        <h2 className="font-display text-3xl font-semibold text-zinc-50 md:text-4xl">
          Your reel is ready
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-zinc-400">
          {occasion ? `A ${occasion.label} reel` : "A cinematic reel"}, scored and
          sealed with verifiable provenance.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Player */}
        <div className="lg:col-span-3">
          <div className="letterbox aspect-video overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-900 shadow-film">
            {playbackUrl ? (
              <video controls playsInline className="h-full w-full" src={playbackUrl}>
                Your browser does not support the video tag.
              </video>
            ) : (
              <ReelPoster
                gradient={theme.gradient}
                thumbUrls={photos.slice(0, 4).map((p) => p.url)}
              />
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="gold">{reel.reel_name}</Badge>
            {occasion && <Badge variant="neutral">{occasion.aspect_ratio}</Badge>}
            {occasion && (
              <Badge variant="muted">{occasion.music_style}</Badge>
            )}
            {degraded && (
              <Badge
                variant="neutral"
                className="border-amber-400/30 bg-amber-400/10 text-amber-200"
                title={DEGRADE_NOTE}
              >
                <Clapperboard className="h-3.5 w-3.5" />
                Rendered on the built-in offline generator
              </Badge>
            )}
          </div>
          {degraded && (
            <p className="mt-2 text-xs text-zinc-500">{DEGRADE_NOTE}</p>
          )}

          <div className="mt-6">
            <ShareBar reel={reel} />
          </div>
        </div>

        {/* Provenance */}
        <div className="lg:col-span-2">
          <ProvenancePanel reel={reel} />
        </div>
      </div>

      <div className="mt-10 flex justify-center">
        <Button variant="outline" size="lg" onClick={reset}>
          <RotateCcw className="h-5 w-5" />
          Create another reel
        </Button>
      </div>
    </div>
  );
}

/** Cinematic poster shown when the reel isn't browser-playable — the offline
 *  generator's deterministic bytes are real sealed artifacts, not decodable
 *  video. Builds a mosaic from the user's own photos. */
function ReelPoster({
  gradient,
  thumbUrls,
}: {
  gradient: string;
  thumbUrls: string[];
}) {
  return (
    <div className="relative grid h-full place-items-center">
      {thumbUrls.length > 0 ? (
        <div className="absolute inset-0 grid grid-cols-2 gap-px opacity-40">
          {thumbUrls.map((u, i) => (
            <img key={i} src={u} alt="" className="h-full w-full object-cover" />
          ))}
        </div>
      ) : (
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient} to-ink-900`} />
      )}
      <div className="absolute inset-0 bg-ink-950/50" />
      <div className="relative flex flex-col items-center text-center">
        <PlayCircle className="h-14 w-14 text-white/80" />
        <p className="mt-3 max-w-xs px-6 text-sm text-white/70">
          The preview plays when the reel comes from live AI generation.
          Provenance is fully sealed and verifiable now →
        </p>
      </div>
    </div>
  );
}
