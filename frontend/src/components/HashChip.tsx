import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { shortHash } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function HashChip({
  hash,
  label,
  className,
}: {
  hash: string | null | undefined;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    if (!hash) return;
    try {
      await navigator.clipboard.writeText(hash);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — non-fatal */
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      disabled={!hash}
      title={hash ? `${label ? label + ": " : ""}${hash} — click to copy` : "unavailable"}
      className={cn(
        "group inline-flex items-center gap-1.5 rounded-md border border-white/[0.08] bg-ink-900/70 px-2 py-1 font-mono text-xs text-zinc-300 transition-colors hover:border-gold-400/40 hover:text-gold-200 disabled:opacity-50",
        className,
      )}
    >
      <span className="tabular-nums">{shortHash(hash)}</span>
      {copied ? (
        <Check className="h-3 w-3 text-emerald-400" />
      ) : (
        <Copy className="h-3 w-3 opacity-50 group-hover:opacity-100" />
      )}
    </button>
  );
}
