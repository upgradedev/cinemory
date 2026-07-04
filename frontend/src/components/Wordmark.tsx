import { Clapperboard } from "lucide-react";
import { cn } from "@/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-gold-300 to-gold-600 shadow-glow-sm">
        <Clapperboard className="h-5 w-5 text-ink-950" strokeWidth={2.25} />
      </span>
      <span className="font-display text-2xl font-semibold tracking-tight text-zinc-50">
        Cine<span className="text-gradient-gold">mory</span>
      </span>
    </div>
  );
}
