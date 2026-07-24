import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        gold: "border-gold-400/30 bg-gold-400/10 text-gold-200",
        verified: "border-emerald-400/30 bg-emerald-400/10 text-emerald-300",
        neutral: "border-white/10 bg-white/[0.04] text-zinc-300",
        muted: "border-white/[0.06] bg-transparent text-zinc-400",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
