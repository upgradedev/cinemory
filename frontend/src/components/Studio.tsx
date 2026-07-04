import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Stepper } from "./Stepper";
import { PhotoUpload } from "./steps/PhotoUpload";
import { OccasionPicker } from "./steps/OccasionPicker";
import { GenerateReel } from "./steps/GenerateReel";
import { ReelResult } from "./steps/ReelResult";
import { useReelStore } from "@/store/useReelStore";
import type { ReelResponse } from "@/lib/api";

export function Studio() {
  const step = useReelStore((s) => s.step);
  const goTo = useReelStore((s) => s.goTo);
  const [reel, setReel] = useState<ReelResponse | null>(null);

  return (
    <section className="container max-w-4xl py-12 md:py-16">
      <Stepper current={step} />

      <AnimatePresence mode="wait">
        <motion.div
          key={step}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -24 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
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
          {step === "result" &&
            (reel ? (
              <ReelResult reel={reel} />
            ) : (
              <PhotoUpload />
            ))}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}
