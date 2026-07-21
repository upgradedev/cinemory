// Generation progress model.
//
// The staged front-load is honest (it paces the fixed server pipeline), but it
// used to park at ~86% while the request was still in flight — a bar that
// looks frozen exactly when the app is doing its real work. The tail now keeps
// crawling asymptotically against real elapsed time: it approaches (but never
// fakes) completion, and only the server response lands 100.

/** Percent for the staged front-load (unchanged behavior: caps one stage
 *  short of the end while the request is pending). */
export function stagedFrontPct(stage: number, totalStages: number): number {
  return Math.round((Math.min(stage, totalStages - 1) / totalStages) * 100);
}

/** Time constant of the asymptotic tail: ~63% of the remaining headroom is
 *  consumed every TAIL_TAU_MS while the response is still pending. */
export const TAIL_TAU_MS = 12_000;

/** The visible ceiling while pending — 100 is reserved for the real response. */
export const PENDING_CEIL_PCT = 99;

/**
 * Smooth overall progress:
 *  - `done` → 100 (only the landed response completes the bar);
 *  - before the last visible stage → the honest staged front-load;
 *  - at the last stage → the front-load plus an asymptotic ease of the
 *    remaining headroom against `tailElapsedMs`, capped at 99.
 * Monotonic in both `stage` and `tailElapsedMs`.
 */
export function generationProgressPct(opts: {
  stage: number;
  totalStages: number;
  tailElapsedMs: number;
  done: boolean;
}): number {
  const { stage, totalStages, tailElapsedMs, done } = opts;
  if (done) return 100;
  const front = stagedFrontPct(stage, totalStages);
  if (stage < totalStages - 1 || tailElapsedMs <= 0) return front;
  const headroom = PENDING_CEIL_PCT - front;
  const eased = headroom * (1 - Math.exp(-tailElapsedMs / TAIL_TAU_MS));
  return Math.min(PENDING_CEIL_PCT, Math.round(front + eased));
}
