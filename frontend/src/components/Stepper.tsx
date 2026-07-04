import { Check } from "lucide-react";
import { motion } from "framer-motion";
import type { Step } from "@/store/useReelStore";
import { cn } from "@/lib/utils";

const STEPS: { key: Step; label: string }[] = [
  { key: "upload", label: "Photos" },
  { key: "occasion", label: "Occasion" },
  { key: "generate", label: "Generate" },
  { key: "result", label: "Reel" },
];

export function Stepper({ current }: { current: Step }) {
  const currentIndex = STEPS.findIndex((s) => s.key === current);

  return (
    <nav aria-label="Progress" className="mx-auto mb-10 w-full max-w-lg">
      <ol className="flex items-center">
        {STEPS.map((s, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <li key={s.key} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <span
                  className={cn(
                    "grid h-8 w-8 place-items-center rounded-full border text-xs font-semibold transition-colors",
                    done && "border-gold-400 bg-gold-400 text-ink-950",
                    active &&
                      "border-gold-400 bg-gold-400/15 text-gold-200 shadow-glow-sm",
                    !done && !active && "border-white/10 bg-ink-800 text-zinc-500",
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  {done ? <Check className="h-4 w-4" /> : i + 1}
                </span>
                <span
                  className={cn(
                    "text-xs font-medium",
                    active ? "text-zinc-200" : "text-zinc-500",
                  )}
                >
                  {s.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div className="mx-2 h-px flex-1 overflow-hidden bg-white/10">
                  <motion.div
                    className="h-full bg-gold-400"
                    initial={false}
                    animate={{ width: done ? "100%" : "0%" }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
