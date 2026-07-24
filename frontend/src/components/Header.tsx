import { motion } from "framer-motion";
import { Wordmark } from "./Wordmark";
import { Badge } from "./ui/badge";
import { useHealth } from "@/lib/queries";

/** Plain-English tooltip for the health badge — "live" is jargon otherwise. */
export function modeTooltip(mode: string): string {
  if (mode === "live") return "Backend health: live = real B2 storage wired";
  if (mode === "offline")
    return "Backend health: offline = running on the built-in deterministic backends (no cloud credentials needed)";
  return `Backend health: mode "${mode}"`;
}

export function Header() {
  const health = useHealth();

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="sticky top-0 z-40 border-b border-white/[0.05] bg-ink-950/70 backdrop-blur-xl"
    >
      <div className="container flex h-16 items-center justify-between">
        <a
          href="/"
          className="inline-flex min-h-11 items-center rounded-lg"
          aria-label="Cinemory home"
        >
          <Wordmark />
        </a>
        <div className="flex items-center gap-3">
          {health.isSuccess && (
            <Badge variant="verified" title={modeTooltip(health.data.mode)}>
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
              </span>
              API live · {health.data.mode}
            </Badge>
          )}
          {health.isError && (
            <Badge variant="muted" title="Backend unreachable">
              API offline
            </Badge>
          )}
        </div>
      </div>
    </motion.header>
  );
}
