import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, Loader2, RotateCw } from "lucide-react";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";
import { StepHeading } from "./PhotoUpload";
import { useCreateReel, useOccasions, useUploadReel } from "@/lib/queries";
import { deriveReelShape, useReelStore } from "@/store/useReelStore";
import type { ReelResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const STAGES = [
  "Reading your photos",
  "Generating cinematic clips",
  "Composing chapter bridges",
  "Scoring music-driven cuts",
  "Stitching the final reel",
  "Uploading to Backblaze B2",
  "Sealing cryptographic provenance",
];

export function GenerateReel({
  onComplete,
}: {
  onComplete: (reel: ReelResponse) => void;
}) {
  const photos = useReelStore((s) => s.photos);
  const occasionKey = useReelStore((s) => s.occasionKey);
  const goTo = useReelStore((s) => s.goTo);
  const { data: occasions } = useOccasions();
  const uploadMutation = useUploadReel();
  const synthMutation = useCreateReel();

  const [stage, setStage] = useState(0);
  const startedRef = useRef(false);

  const occasion = occasions?.find((o) => o.key === occasionKey);
  const shape = deriveReelShape(photos.length);

  // Real photos → send the actual bytes to /reels/upload-multipart. With no
  // files selected we fall back to the synthetic count/order path (/reels).
  const hasPhotos = photos.length > 0;
  const mutation = hasPhotos ? uploadMutation : synthMutation;

  const start = () => {
    setStage(0);
    const onSettled = {
      onSuccess: (reel: ReelResponse) => {
        setStage(STAGES.length);
        window.setTimeout(() => onComplete(reel), 650);
      },
    };
    if (hasPhotos) {
      uploadMutation.mutate(
        {
          name: "cinemory-reel",
          occasion: occasionKey ?? "anniversary",
          chapters: shape.chapters,
          files: photos.map((p) => p.file),
        },
        onSettled,
      );
    } else {
      synthMutation.mutate(
        {
          name: "cinemory-reel",
          occasion: occasionKey ?? "anniversary",
          chapters: shape.chapters,
          per_chapter: shape.per_chapter,
        },
        onSettled,
      );
    }
  };

  // Kick off exactly once on mount.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    start();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Advance the visible pipeline stage while the request is in flight. This is
  // an honest reflection of the fixed server pipeline (POST /reels is
  // synchronous); we pace the stage list to feel like the work it represents.
  useEffect(() => {
    if (!mutation.isPending) return;
    const id = window.setInterval(() => {
      setStage((s) => (s < STAGES.length - 1 ? s + 1 : s));
    }, 900);
    return () => window.clearInterval(id);
  }, [mutation.isPending]);

  const pct = mutation.isSuccess
    ? 100
    : Math.round((Math.min(stage, STAGES.length - 1) / STAGES.length) * 100);

  if (mutation.isError) {
    return (
      <div className="animate-fade-up">
        <StepHeading
          title="The reel didn’t finish"
          subtitle="Something interrupted the render. Your photos and occasion are safe — try again."
        />
        <div className="glass mx-auto max-w-md rounded-2xl p-8 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-ember-500/15 text-ember-400">
            <AlertTriangle className="h-6 w-6" />
          </span>
          <p className="mt-4 text-sm text-zinc-400">
            {mutation.error instanceof Error
              ? mutation.error.message
              : "Unknown error."}
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Button variant="ghost" onClick={() => goTo("occasion")}>
              Back
            </Button>
            <Button onClick={start}>
              <RotateCw className="h-4 w-4" />
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up">
      <StepHeading
        title="Rolling…"
        subtitle={
          occasion
            ? `Editing a ${occasion.label.toLowerCase()} reel — ${occasion.music_style}.`
            : "Your cinematic reel is being composed."
        }
      />

      <div className="mx-auto max-w-lg">
        {/* Reel animation */}
        <div className="letterbox mb-8 grid aspect-video place-items-center overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-900 shadow-film">
          <div className="relative">
            <div className="h-16 w-16 animate-reel-spin rounded-full border-2 border-gold-400/30 border-t-gold-400" />
            <Loader2 className="absolute inset-0 m-auto h-6 w-6 animate-pulse text-gold-300" />
          </div>
        </div>

        <div className="mb-6 flex items-center justify-between text-sm">
          <span className="text-zinc-400">
            {shape.chapters} chapters · {photos.length}{" "}
            {photos.length === 1 ? "photo" : "photos"}
          </span>
          <span className="font-mono text-gold-300">{pct}%</span>
        </div>
        <Progress value={pct} indeterminate={mutation.isPending} />

        <ol className="mt-8 space-y-3">
          {STAGES.map((label, i) => {
            const done = i < stage || mutation.isSuccess;
            const active = i === stage && mutation.isPending;
            return (
              <li
                key={label}
                className={cn(
                  "flex items-center gap-3 text-sm transition-colors",
                  done
                    ? "text-zinc-300"
                    : active
                      ? "text-zinc-100"
                      : "text-zinc-600",
                )}
              >
                <span
                  className={cn(
                    "grid h-6 w-6 shrink-0 place-items-center rounded-full border transition-colors",
                    done && "border-gold-400 bg-gold-400 text-ink-950",
                    active && "border-gold-400 text-gold-300",
                    !done && !active && "border-white/10",
                  )}
                >
                  <AnimatePresence mode="wait" initial={false}>
                    {done ? (
                      <motion.span
                        key="done"
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                      >
                        <Check className="h-3.5 w-3.5" />
                      </motion.span>
                    ) : active ? (
                      <Loader2 key="spin" className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <span key="idle" className="text-[10px]">
                        {i + 1}
                      </span>
                    )}
                  </AnimatePresence>
                </span>
                {label}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
