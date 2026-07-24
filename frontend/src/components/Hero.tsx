import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Film, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { Button } from "./ui/button";
import { ExampleReel } from "./ExampleReel";

const features = [
  {
    icon: Film,
    title: "Cinematic by default",
    body: "Music-driven cuts, chapter bridges and title cards — an editor’s eye, automated.",
  },
  {
    icon: Sparkles,
    title: "Occasion-aware",
    body: "Anniversary, wedding, graduation, year-in-review — each with its own pacing and score.",
  },
  {
    icon: ShieldCheck,
    title: "Provenance-sealed",
    body: "Every asset is SHA-256 hashed and the manifest is sealed — verifiable, tamper-evident.",
  },
];

export function Hero({
  onStart,
  onTrySamples,
}: {
  onStart: () => void;
  /** Optional zero-friction demo entry — generates the sample set and jumps
   *  straight into the studio. When omitted the secondary CTA is hidden. */
  onTrySamples?: () => void | Promise<void>;
}) {
  const [sampling, setSampling] = useState(false);
  const trySamples = async () => {
    if (!onTrySamples) return;
    setSampling(true);
    try {
      await onTrySamples();
    } finally {
      setSampling(false);
    }
  };

  return (
    <section className="relative overflow-hidden">
      {/* Ambient cinematic light beams */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-70"
        style={{
          background:
            "conic-gradient(from 210deg at 50% 0%, transparent 0deg, rgba(216,178,90,0.08) 40deg, transparent 90deg, rgba(226,84,58,0.06) 140deg, transparent 200deg)",
        }}
      />

      <div className="container flex flex-col items-center py-20 text-center md:py-28">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="mb-6 inline-flex items-center gap-2 rounded-full border border-gold-400/20 bg-gold-400/5 px-4 py-1.5 text-xs font-medium text-gold-200"
        >
          <Sparkles className="h-3.5 w-3.5" />
          Powered by Genblaze · stored on Backblaze B2
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
          className="max-w-4xl font-display text-5xl font-semibold leading-[1.05] tracking-tight text-zinc-50 md:text-7xl"
        >
          Your memories,
          <br />
          <span className="text-gradient-gold">made into film.</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
          className="mt-6 max-w-xl text-balance text-lg text-zinc-400"
        >
          Cinemory turns a handful of photos into a scored, stitched cinematic
          reel — and seals it with cryptographic provenance you can verify.
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="mt-3 max-w-lg text-sm text-zinc-400"
        >
          Made for families, couples and small teams — no video editor required.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="mt-10 flex flex-col items-center gap-3 sm:flex-row"
        >
          <Button size="lg" onClick={onStart} className="group">
            Create your reel
            <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-0.5" />
          </Button>
          {onTrySamples && (
            <Button
              variant="outline"
              size="lg"
              onClick={trySamples}
              disabled={sampling}
              aria-busy={sampling}
            >
              {sampling ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <Sparkles className="h-5 w-5" />
              )}
              {sampling ? "Preparing samples…" : "Try with sample photos"}
            </Button>
          )}
        </motion.div>
        <span className="mt-4 text-sm text-zinc-400">
          No account · No watermark · ~30 seconds
        </span>

        {/* A live, muted, looping example of the generative output. */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="mt-16 w-full max-w-3xl"
        >
          <ExampleReel />
        </motion.div>
      </div>

      {/* Feature triad */}
      <div className="container grid gap-6 pb-24 md:grid-cols-3">
        {features.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.5, delay: i * 0.08 }}
            className="glass rounded-2xl p-6"
          >
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-gold-400/10 text-gold-300">
              <f.icon className="h-5 w-5" />
            </span>
            <h2 className="mt-4 font-display text-lg font-semibold text-zinc-100">
              {f.title}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{f.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
