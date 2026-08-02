import { motion } from "framer-motion";
import { Wordmark } from "./Wordmark";
import { Badge } from "./ui/badge";
import { AuthMenu } from "./AuthMenu";
import { useHealth } from "@/lib/queries";

/** `onOpenLibrary` is only ever invoked from AuthMenu's signed-in "My reels"
 *  item, which itself renders nothing when Firebase config is absent (see
 *  lib/auth.ts::isAuthEnabled) — a build with no VITE_FIREBASE_* vars (every
 *  build today) never shows the control that could call it. */
export function Header({ onOpenLibrary }: { onOpenLibrary?: () => void }) {
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
        <div className="flex flex-wrap items-center justify-end gap-3">
          {/* Deliberately no "backend healthy" badge: that's an internal ops
              signal, not something a visitor needs to see. The health check
              itself (useHealth() above) still runs; only the success-path
              badge is gone. An unreachable backend is still worth surfacing
              below, since it explains why generation might not work. */}
          {health.isError && (
            <Badge variant="muted" title="Backend unreachable">
              API offline
            </Badge>
          )}
          <AuthMenu onOpenLibrary={onOpenLibrary ?? (() => {})} />
        </div>
      </div>
    </motion.header>
  );
}
