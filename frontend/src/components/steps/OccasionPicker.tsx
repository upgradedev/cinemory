import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Music, Timer } from "lucide-react";
import { Button } from "../ui/button";
import { StepHeading } from "./PhotoUpload";
import { useOccasions } from "@/lib/queries";
import { useReelStore } from "@/store/useReelStore";
import { occasionTheme } from "@/lib/occasion-theme";
import { cn } from "@/lib/utils";
import type { Occasion } from "@/lib/api";

export function OccasionPicker() {
  const { data: occasions, isLoading, isError, refetch } = useOccasions();
  const occasionKey = useReelStore((s) => s.occasionKey);
  const setOccasion = useReelStore((s) => s.setOccasion);
  const goTo = useReelStore((s) => s.goTo);

  return (
    <div className="animate-fade-up">
      <StepHeading
        title="Set the mood"
        subtitle="Each occasion has its own score, pacing and title style — the whole edit changes with your choice."
      />

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-44 animate-pulse rounded-2xl border border-white/[0.06] bg-ink-800/60"
            />
          ))}
        </div>
      )}

      {isError && (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-zinc-300">Couldn’t load occasion presets.</p>
          <Button variant="outline" className="mt-4" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      )}

      {occasions && (
        <div
          role="radiogroup"
          aria-label="Occasion"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {occasions.map((o, i) => (
            <OccasionCard
              key={o.key}
              occasion={o}
              index={i}
              selected={occasionKey === o.key}
              onSelect={() => setOccasion(o.key)}
            />
          ))}
        </div>
      )}

      {/* Stack on mobile (two lg nowrap buttons cannot share a 375px row
          without overflowing); split left/right from >=sm. */}
      <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <Button
          variant="ghost"
          size="lg"
          className="w-full sm:w-auto"
          onClick={() => goTo("upload")}
        >
          <ArrowLeft className="h-5 w-5" />
          Back
        </Button>
        <div className="flex flex-col gap-1.5 sm:items-end">
          <Button
            size="lg"
            className="w-full sm:w-auto"
            disabled={!occasionKey}
            aria-describedby={!occasionKey ? "occasion-cta-hint" : undefined}
            onClick={() => goTo("generate")}
          >
            Generate my reel
            <ArrowRight className="h-5 w-5" />
          </Button>
          {!occasionKey && (
            <p
              id="occasion-cta-hint"
              className="text-center text-xs text-zinc-400 sm:text-right"
            >
              Pick an occasion to continue
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function OccasionCard({
  occasion,
  index,
  selected,
  onSelect,
}: {
  occasion: Occasion;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const theme = occasionTheme(occasion.key);
  return (
    <motion.button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05 }}
      whileHover={{ y: -4 }}
      className={cn(
        "group relative overflow-hidden rounded-2xl border p-5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-400/80",
        selected
          ? "border-gold-400/70 bg-ink-800 shadow-glow-sm"
          : "border-white/[0.06] bg-ink-800/60 hover:border-white/15",
      )}
      style={selected ? { boxShadow: `0 0 40px -14px ${theme.glow}` } : undefined}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-70 transition-opacity group-hover:opacity-100",
          theme.gradient,
        )}
      />
      <div className="relative">
        <div className="flex items-start justify-between">
          <span className="text-3xl" aria-hidden>
            {theme.emoji}
          </span>
          <span
            className={cn(
              "grid h-6 w-6 place-items-center rounded-full border transition-all",
              selected
                ? "border-gold-400 bg-gold-400 text-ink-950"
                : "border-white/20 text-transparent",
            )}
          >
            <Check className="h-3.5 w-3.5" />
          </span>
        </div>
        <h2 className="mt-4 font-display text-lg font-semibold text-zinc-50">
          {occasion.label}
        </h2>
        <p className="mt-0.5 text-sm text-zinc-400">{theme.tagline}</p>

        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <Music className="h-3.5 w-3.5 text-gold-300/80" />
            {occasion.music_style}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Timer className="h-3.5 w-3.5 text-gold-300/80" />
            {occasion.seconds_per_clip}s / clip · {occasion.aspect_ratio}
          </span>
        </div>
      </div>
    </motion.button>
  );
}
