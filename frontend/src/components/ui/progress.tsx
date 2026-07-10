import { cn } from "@/lib/utils";

interface ProgressProps {
  value: number; // 0..100
  className?: string;
  indeterminate?: boolean;
}

export function Progress({ value, className, indeterminate }: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn(
        "relative h-1.5 w-full overflow-hidden rounded-full bg-ink-600",
        className,
      )}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-gold-400 to-ember-400 transition-[width] duration-700 ease-out"
        style={{ width: `${clamped}%` }}
      />
      {indeterminate && (
        <div className="absolute inset-y-0 -left-1/3 w-1/3 animate-shimmer bg-gradient-to-r from-transparent via-white/25 to-transparent" />
      )}
    </div>
  );
}
