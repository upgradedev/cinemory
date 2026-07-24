import { motion } from "framer-motion";
import { ImagePlus, ShieldCheck, Sparkles } from "lucide-react";

const STEPS = [
  {
    icon: ImagePlus,
    title: "Add your photos",
    body: "Drop in a handful of moments — the order you choose becomes the edit.",
  },
  {
    icon: Sparkles,
    title: "Pick an occasion",
    body: "Anniversary, wedding, graduation… each brings its own score, pacing and titles.",
  },
  {
    icon: ShieldCheck,
    title: "Get a sealed reel",
    body: "A cinematic reel you can play, share and cryptographically verify — in seconds.",
  },
];

/** A three-step "how it works" strip so a first-time visitor understands the
 *  whole flow (Photos → Occasion → sealed, verifiable reel) at a glance. */
export function HowItWorks() {
  return (
    <section aria-labelledby="how-it-works-heading" className="container pb-20">
      <h2
        id="how-it-works-heading"
        className="mb-8 text-center font-display text-2xl font-semibold text-zinc-100"
      >
        How it works
      </h2>
      <ol className="grid gap-4 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <motion.li
            key={s.title}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-40px" }}
            transition={{ duration: 0.4, delay: i * 0.08 }}
            className="glass rounded-2xl p-5"
          >
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-xl bg-gold-400/10 text-gold-300">
                <s.icon className="h-5 w-5" />
              </span>
              <span className="font-mono text-xs uppercase tracking-widest text-zinc-400">
                Step {i + 1}
              </span>
            </div>
            <h3 className="mt-4 font-display text-base font-semibold text-zinc-100">
              {s.title}
            </h3>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{s.body}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  );
}
