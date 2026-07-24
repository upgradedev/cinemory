import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Stepper } from "./Stepper";
import { PhotoUpload } from "./steps/PhotoUpload";
import { OccasionPicker } from "./steps/OccasionPicker";
import { GenerateReel } from "./steps/GenerateReel";
import { ReelResult } from "./steps/ReelResult";
import { useReelStore } from "@/store/useReelStore";
import type { ReelResponse } from "@/lib/api";

const STEP_LABEL: Record<string, string> = {
  upload: "Step 1 of 4: choose your photos",
  occasion: "Step 2 of 4: choose an occasion",
  generate: "Step 3 of 4: generating your reel",
  result: "Step 4 of 4: your reel is ready",
};

export function Studio() {
  const step = useReelStore((s) => s.step);
  const goTo = useReelStore((s) => s.goTo);
  const [reel, setReel] = useState<ReelResponse | null>(null);
  const regionRef = useRef<HTMLDivElement>(null);
  const reduceMotion = useReducedMotion();

  // Move keyboard/screen-reader focus to the new step on each transition so
  // the wizard is navigable without a mouse, and announce it via aria-live.
  useEffect(() => {
    regionRef.current?.focus();
  }, [step]);

  return (
    <section className="container max-w-4xl py-12 md:py-16">
      <Stepper current={step} />

      <p className="sr-only" role="status" aria-live="polite">
        {STEP_LABEL[step]}
      </p>

      {/* Each step is a fresh keyed subtree that mounts and runs its own enter
          animation immediately on every step change. We deliberately do NOT
          wrap this in AnimatePresence mode="wait": that mode defers the
          incoming step's animation until the OUTGOING step's exit completes,
          and when that exit is throttled or dropped (a backgrounded tab, some
          headless environments) the new step stays stuck at its initial
          opacity:0 and the wizard blanks — the panel-2 dead-end. Mounting the
          incoming step unconditionally makes the transition robust regardless
          of exit timing, and prefers-reduced-motion renders it instantly with
          no transform. */}
      <motion.div
        key={step}
        ref={regionRef}
        tabIndex={-1}
        role="group"
        aria-label={STEP_LABEL[step]}
        className="outline-none"
        initial={reduceMotion ? false : { opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={reduceMotion ? { duration: 0 } : { duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        {step === "upload" && <PhotoUpload />}
        {step === "occasion" && <OccasionPicker />}
        {step === "generate" && (
          <GenerateReel
            onComplete={(r) => {
              setReel(r);
              goTo("result");
            }}
          />
        )}
        {step === "result" && (reel ? <ReelResult reel={reel} /> : <PhotoUpload />)}
      </motion.div>
    </section>
  );
}
