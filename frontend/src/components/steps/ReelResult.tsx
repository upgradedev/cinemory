import { motion } from "framer-motion";
import { Clapperboard, PartyPopper, PlayCircle, RotateCcw } from "lucide-react";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { KenBurnsSlideshow } from "../KenBurnsSlideshow";
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
        <h1 className="font-display text-3xl font-semibold text-zinc-50 md:text-4xl">
          Your reel is ready
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-zinc-400">
          {occasion ? `A ${occasion.label} reel` : "A cinematic reel"}, scored and
          sealed with verifiable provenance.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Player. min-w-0 lets the grid column actually shrink on resize —
            without it the letterbox keeps a stale min-content width and the
            page overflows horizontally on narrow viewports. The aspect box is
            width-driven and the media fills it absolutely, so its height can
            never go stale either. */}
        <div className="min-w-0 lg:col-span-3">
          <div className="letterbox relative aspect-video w-full overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-900 shadow-film">
            {playbackUrl ? (
              <video
                controls
                playsInline
                className="absolute inset-0 h-full w-full"
                src={playbackUrl}
              >
                Your browser does not support the video tag.
              </video>
            ) : (
              <>
                {photos.length > 0 ? (
                  <KenBurnsSlideshow
                    photos={photos.map((p) => ({ url: p.url, name: p.name }))}
                  />
                ) : (
                  <ReelPoster gradient={theme.gradient} />
                )}
                {degraded && (
                  <div className="absolute left-3 top-[12%] z-20">
                    <Badge
                      variant="neutral"
                      className="border-amber-400/30 bg-ink-950/70 text-amber-200 backdrop-blur-sm"
                      title={DEGRADE_NOTE}
                    >
                      <Clapperboard className="h-3.5 w-3.5" />
                      Rendered on the built-in offline generator
                    </Badge>
                  </div>
                )}
                {photos.length > 0 && (
                  <p className="absolute inset-x-0 bottom-[11%] z-20 px-6 text-center text-xs text-white/70">
                    Preview slideshow of your photos — the reel file plays here
                    when it comes from live AI generation.
                  </p>
                )}
              </>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="gold">{reel.reel_name}</Badge>
            {occasion && <Badge variant="neutral">{occasion.aspect_ratio}</Badge>}
            {occasion && (
              <Badge variant="muted">{occasion.music_style}</Badge>
            )}
          </div>
          {degraded && (
            <p className="mt-2 text-xs text-zinc-400">{DEGRADE_NOTE}</p>
          )}

          <div className="mt-6">
            <ShareBar reel={reel} />
          </div>
        </div>

        {/* Provenance */}
        <div className="min-w-0 lg:col-span-2">
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

/** Cinematic poster for the empty edge case: no playable video AND no local
 *  photos to slideshow (e.g. a synthetic run after a page refresh cleared the
 *  storyboard). Everything else gets the Ken Burns slideshow. */
function ReelPoster({ gradient }: { gradient: string }) {
  return (
    <div className="absolute inset-0 grid place-items-center">
      <div className={`absolute inset-0 bg-gradient-to-br ${gradient} to-ink-900`} />
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
