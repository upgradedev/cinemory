import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { renderSampleSceneDataUrls } from "@/lib/sample-photos";
import { cn } from "@/lib/utils";

// Evocative captions that rotate with the frames — conveys "occasion-aware".
const CAPTIONS = ["Anniversary", "Wedding", "Graduation", "Year in Review", "Birthday"];

/**
 * Autoplaying, muted, looping preview of the generative output: the very same
 * deterministic synthetic scenes the app can produce, crossfading with a slow
 * Ken Burns pan so a judge sees what Cinemory makes within the first seconds.
 * Client-rendered (no bundled assets); falls back to a static filmstrip where
 * Canvas 2D is unavailable (jsdom, ancient browsers). Honors reduced motion.
 */
export function ExampleReel() {
  const [frames, setFrames] = useState<string[]>([]);
  const [failed, setFailed] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    try {
      const urls = renderSampleSceneDataUrls();
      if (urls.length > 0) setFrames(urls);
      else setFailed(true);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    if (frames.length === 0) return;
    const reduce =
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
    if (reduce) return; // hold a single frame; no auto-advance
    const id = window.setInterval(
      () => setActive((i) => (i + 1) % frames.length),
      2600,
    );
    return () => window.clearInterval(id);
  }, [frames.length]);

  if (failed || frames.length === 0) return <ExampleReelFallback />;

  return (
    <div
      role="img"
      aria-label="Example Cinemory reel — a cinematic sequence generated from photos"
      className="letterbox relative aspect-video w-full overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-900 shadow-film"
    >
      {frames.map((src, i) => (
        <img
          key={i}
          src={src}
          alt=""
          aria-hidden
          className={cn(
            "kb-slide",
            i % 2 === 0 ? "kb-pan-a" : "kb-pan-b",
            i === active && "kb-slide-active",
          )}
        />
      ))}
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-t from-ink-950/70 via-transparent to-ink-950/10"
      />
      <span
        aria-hidden
        className="absolute left-4 top-[12%] z-20 inline-flex items-center gap-1.5 rounded-full bg-ink-950/70 px-3 py-1 text-xs font-medium text-gold-200 backdrop-blur-sm"
      >
        <Play className="h-3 w-3 fill-current" />
        Example reel
      </span>
      <p
        aria-hidden
        className="absolute inset-x-0 bottom-[16%] z-20 text-center font-display text-xl font-semibold text-white drop-shadow-lg"
      >
        {CAPTIONS[active % CAPTIONS.length]}
      </p>
      <div
        aria-hidden
        className="absolute inset-x-0 bottom-[9%] z-20 flex justify-center gap-1.5"
      >
        {frames.map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1 rounded-full transition-all",
              i === active ? "w-6 bg-gold-300" : "w-1.5 bg-white/40",
            )}
          />
        ))}
      </div>
    </div>
  );
}

/** Static, dependency-free preview shown when scene rendering is unavailable —
 *  the filmstrip motif, so the hero never has an empty frame. */
export function ExampleReelFallback() {
  return (
    <div
      role="img"
      aria-label="Cinemory reel filmstrip preview"
      className="letterbox aspect-video w-full overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-800 shadow-film"
    >
      <div className="grid h-full grid-cols-4 gap-px bg-black/40">
        {["from-rose-500/30", "from-amber-400/30", "from-violet-500/30", "from-sky-400/30"].map(
          (g, i) => (
            <div
              key={i}
              aria-hidden
              className={`bg-gradient-to-br ${g} to-ink-900 flex items-end p-4`}
            >
              <span className="font-mono text-[10px] uppercase tracking-widest text-white/40">
                Ch.{i + 1}
              </span>
            </div>
          ),
        )}
      </div>
    </div>
  );
}
