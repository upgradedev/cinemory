import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-400/80 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-950 disabled:pointer-events-none disabled:opacity-40 select-none",
  {
    variants: {
      variant: {
        primary:
          "bg-gradient-to-b from-gold-300 to-gold-500 text-ink-950 font-semibold shadow-glow-sm hover:shadow-glow hover:brightness-110 active:scale-[0.98]",
        secondary:
          "glass text-zinc-100 hover:bg-white/[0.06] hover:border-white/10 active:scale-[0.98]",
        ghost: "text-zinc-300 hover:bg-white/[0.05] hover:text-zinc-100",
        outline:
          "border border-gold-400/40 text-gold-200 hover:bg-gold-400/10 hover:border-gold-400/70 active:scale-[0.98]",
      },
      // Mobile-first tap targets: every control clears the 44px WCAG 2.5.5
      // minimum on touch viewports, then tightens to its compact desktop size
      // at >=sm (640px) so the dense premium layout is preserved.
      size: {
        sm: "h-11 px-4 text-xs sm:h-9",
        md: "h-11 px-6",
        lg: "h-14 px-9 text-base",
        icon: "h-11 w-11 sm:h-10 sm:w-10",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
