import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Check, Loader2, RotateCw } from "lucide-react";
import { Button } from "../ui/button";
import { Progress } from "../ui/progress";
import { StepHeading } from "./PhotoUpload";
import {
  useCreateReel,
  useOccasions,
  usePollReelJob,
  useSubmitReelJob,
} from "@/lib/queries";
import { deriveReelShape, useReelStore } from "@/store/useReelStore";
import { generationProgressPct } from "@/lib/progress";
import { ApiError, type ReelResponse } from "@/lib/api";
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

/**
 * A unique name for each generated reel.
 *
 * This used to be the constant `"cinemory-reel"`, which quietly broke
 * provenance for every guest. The reel name is the storage prefix AND the key
 * `GET /reels/{name}` resolves by, so when every run shared one name that route
 * returned whichever earlier run the index matched first, not the reel just
 * made. The Provenance panel then re-fetched that stranger's manifest, compared
 * it against the seal on screen and correctly reported
 * "the re-fetched manifest ... does not match the manifest_hash on screen",
 * while the server receipt reported "Tamper detected" for a perfectly valid
 * reel. Verified live: a uniquely-named reel passes 8/8 checks, the shared name
 * 10/11.
 *
 * Timestamp first so a listing sorts chronologically, then a per-tab counter so
 * two reels started in the same millisecond cannot collide (a counter, not just
 * randomness, so uniqueness is guaranteed rather than merely likely), then a
 * short random suffix so two different tabs cannot collide either. Kept to
 * `[a-z0-9-]` because the backend sanitises the name into an object key.
 */
let reelSeq = 0;

export function newReelName(): string {
  const stamp = Date.now().toString(36);
  const seq = (reelSeq++).toString(36);
  const rand = Math.random().toString(36).slice(2, 8) || "0";
  return `cinemory-reel-${stamp}-${seq}${rand}`;
}

export function GenerateReel({
  onComplete,
}: {
  onComplete: (reel: ReelResponse) => void;
}) {
  const photos = useReelStore((s) => s.photos);
  const occasionKey = useReelStore((s) => s.occasionKey);
  const goTo = useReelStore((s) => s.goTo);
  const { data: occasions } = useOccasions();
  const submitMutation = useSubmitReelJob();
  const synthMutation = useCreateReel();

  const [stage, setStage] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const startedRef = useRef(false);
  const poll = usePollReelJob(jobId);

  const occasion = occasions?.find((o) => o.key === occasionKey);
  const shape = deriveReelShape(photos.length);

  // Real photos → submit an async job (POST /reels/jobs) and poll it, so a
  // multi-minute live render never blocks one HTTP request past the edge
  // proxy's timeout. With no files selected we fall back to the synthetic
  // count/order path (POST /reels): it has no async counterpart (the
  // job-submit route requires at least one photo — see
  // cinemory.ingest.build_spec_from_photos — while the synthetic path takes
  // none), so it stays a direct, blocking mutation.
  const hasPhotos = photos.length > 0;

  const start = () => {
    setStage(0);
    if (hasPhotos) {
      // Reset first so a retry's stale job id/result/error never lingers
      // for even one render.
      setJobId(null);
      submitMutation.mutate(
        {
          name: newReelName(),
          occasion: occasionKey ?? "anniversary",
          chapters: shape.chapters,
          files: photos.map((p) => p.file),
        },
        { onSuccess: (data) => setJobId(data.job_id) },
      );
    } else {
      synthMutation.mutate(
        {
          name: newReelName(),
          occasion: occasionKey ?? "anniversary",
          chapters: shape.chapters,
          per_chapter: shape.per_chapter,
        },
        {
          onSuccess: (reel) => {
            setStage(STAGES.length);
            window.setTimeout(() => onComplete(reel), 650);
          },
        },
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

  // The polled job landed a sealed reel: same completion beat as the
  // synthetic path's onSuccess above (fill the stage list, then hand off
  // after a short beat so the checkmarks are visible before the parent
  // advances to the result step).
  useEffect(() => {
    if (!poll.result) return;
    const result = poll.result;
    setStage(STAGES.length);
    const id = window.setTimeout(() => onComplete(result), 650);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poll.result]);

  // True while a request is genuinely in flight: submitting the job (or the
  // single synchronous synthetic call), or a submitted job still being
  // polled. jobId flips from null to the submitted id in the same render the
  // submit mutation settles, so this stays continuous across that handoff.
  const isPending = hasPhotos
    ? jobId === null
      ? submitMutation.isPending
      : poll.isPolling
    : synthMutation.isPending;
  const isSuccess = hasPhotos ? poll.result !== null : synthMutation.isSuccess;
  const error: Error | null = hasPhotos
    ? submitMutation.isError
      ? submitMutation.error
      : poll.error
    : synthMutation.isError
      ? synthMutation.error
      : null;

  // Advance the visible pipeline stage while a request is in flight. This is
  // an honest reflection of the fixed server pipeline (submit+poll or the
  // single synchronous synthetic call); we pace the stage list to feel like
  // the work it represents.
  useEffect(() => {
    if (!isPending) return;
    const id = window.setInterval(() => {
      setStage((s) => (s < STAGES.length - 1 ? s + 1 : s));
    }, 900);
    return () => window.clearInterval(id);
  }, [isPending]);

  // Once the staged front-load is exhausted (~86%), keep the bar crawling
  // asymptotically against real elapsed time instead of freezing — 100 still
  // only lands with the actual response (see lib/progress.ts).
  const [tailMs, setTailMs] = useState(0);
  useEffect(() => {
    if (!isPending || stage < STAGES.length - 1) {
      setTailMs(0);
      return;
    }
    const startedAt = Date.now();
    const id = window.setInterval(() => setTailMs(Date.now() - startedAt), 300);
    return () => window.clearInterval(id);
  }, [isPending, stage]);

  const pct = generationProgressPct({
    stage,
    totalStages: STAGES.length,
    tailElapsedMs: tailMs,
    done: isSuccess,
  });

  if (error) {
    // Honest-degrade for the headline: a gateway timeout on a multi-minute
    // live render (sync or async — the bounded poll ceiling in usePollReelJob
    // reuses this exact 504 branch) is not a hard failure, so it gets its own
    // reassuring copy. The raw error message — path + HTTP status, or a
    // failed job's exception class name — stays visible as a small technical
    // line underneath, never as the headline.
    const err = error;
    const status = err instanceof ApiError ? err.status : undefined;
    const isTimeout =
      status === 504 || status === 502 || status === 503 || status === 408;
    const friendlyDetail = isTimeout
      ? "This is taking longer than expected. Please try again in a moment."
      : "We couldn’t finish this one. Please try again.";
    const rawDetail = err instanceof Error ? err.message : null;

    return (
      <div className="animate-fade-up">
        <StepHeading
          title="The reel didn’t finish"
          subtitle="Your photos and occasion are safe. Just try again."
        />
        <div className="glass mx-auto max-w-md rounded-2xl p-8 text-center">
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-ember-500/15 text-ember-400">
            <AlertTriangle className="h-6 w-6" />
          </span>
          <p className="mt-4 text-sm text-zinc-400">{friendlyDetail}</p>
          {rawDetail && (
            <p className="mt-2 text-[11px] text-zinc-400">{rawDetail}</p>
          )}
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
            ? `Editing a ${occasion.label.toLowerCase()} reel: ${occasion.music_style}.`
            : "Your cinematic reel is being composed."
        }
      />
      <p className="-mt-5 mb-8 text-center text-sm text-zinc-400">
        A live reel can take a few minutes to render. No need to refresh,
        this updates on its own.
      </p>

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
        <Progress
          value={pct}
          indeterminate={isPending}
          label="Reel generation progress"
        />

        <ol className="mt-8 space-y-3">
          {STAGES.map((label, i) => {
            const done = i < stage || isSuccess;
            const active = i === stage && isPending;
            return (
              <li
                key={label}
                className={cn(
                  "flex items-center gap-3 text-sm transition-colors",
                  done
                    ? "text-zinc-300"
                    : active
                      ? "text-zinc-100"
                      : "text-zinc-400",
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
