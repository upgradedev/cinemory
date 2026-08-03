/**
 * The time budget of one reel, and the photo cap that falls out of it.
 *
 * Every number here is measured, not guessed, and the cap is DERIVED from them
 * rather than typed in by hand — so if the ceiling or the measurement ever
 * changes, the cap moves with it instead of quietly going stale.
 *
 * The arithmetic, in full:
 *
 *   budget            720 s   (REEL_JOB_MAX_POLL_MS, the app's poll ceiling)
 *   fixed overhead   - 45 s   (RUN_OVERHEAD_SECONDS)
 *                    ------
 *   left to generate  675 s
 *   per photo        / 314 s  (LIVE_SECONDS_PER_PHOTO, measured live)
 *                    ------
 *   photos             2.14   -> floor -> 2
 *
 * Live generation is strictly SEQUENTIAL, one call per photo (see
 * `cinemory.pipeline.ReelPipeline.run`: a plain nested loop over chapters and
 * photos, each call blocking), so n photos cost n x 314 s of wall clock. That
 * is why the cap is a division and not a bigger number: three photos need
 * ~987 s, which cannot fit in a 720 s window no matter how the work is
 * arranged on this code path.
 *
 * The cap is a property of THIS demo's waiting window, not of the reel maker,
 * which happily accepts up to 60 photos server-side (`cinemory.ingest`). The
 * UI says so in those words rather than implying a product limit.
 */

/**
 * Bounded total poll duration (~12 min) before the app gives up on a submitted
 * job and surfaces the honest "taking longer than expected" state.
 *
 * Lives here rather than in `queries.ts` (which re-exports it, so every
 * existing importer is unchanged) because it is the numerator of the cap
 * arithmetic above: keeping the ceiling and the cap in one file is what stops
 * one of them being edited without the other.
 */
export const REEL_JOB_MAX_POLL_MS = 12 * 60_000;

/**
 * Measured wall clock of ONE live image-to-video generation, per photo, in
 * seconds. Measured on the deployed service, 2026-08-03.
 */
export const LIVE_SECONDS_PER_PHOTO = 314;

/**
 * Everything in a run that is not per-photo generation: sending the photos up,
 * hosting them for the model to read, stitching the clips, writing every
 * artifact to storage, and sealing the manifest. Held back from the generation
 * budget so the cap has real headroom rather than exactly filling the window.
 */
export const RUN_OVERHEAD_SECONDS = 45;

/**
 * The most photos one reel can hold in this deployment, derived from the
 * budget above. Never below 1, so a pathological config can still make a reel.
 */
export const MAX_REEL_PHOTOS = Math.max(
  1,
  Math.floor((REEL_JOB_MAX_POLL_MS / 1000 - RUN_OVERHEAD_SECONDS) / LIVE_SECONDS_PER_PHOTO),
);

/** Expected wall clock, in seconds, for a reel made from `photoCount` photos. */
export function estimatedRenderSeconds(photoCount: number): number {
  const n = Math.min(Math.max(Math.floor(photoCount) || 0, 1), MAX_REEL_PHOTOS);
  return n * LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS;
}

/**
 * The same estimate as a phrase a visitor reads, e.g. "about 11 minutes".
 * Derived from the photo count, never a fixed string, so it stays true when
 * the count changes.
 */
export function estimatedRenderLabel(photoCount: number): string {
  const minutes = Math.max(1, Math.round(estimatedRenderSeconds(photoCount) / 60));
  return minutes === 1 ? "about a minute" : `about ${minutes} minutes`;
}

/** "1 photo" / "3 photos" — used in several places, so it lives in one. */
export function photoCountLabel(photoCount: number): string {
  return `${photoCount} ${photoCount === 1 ? "photo" : "photos"}`;
}

/**
 * A full sentence estimating the wait, agreeing in number with the count:
 * "1 photo usually takes about 6 minutes." / "2 photos usually take about 11
 * minutes."
 */
export function estimateSentence(photoCount: number): string {
  const verb = photoCount === 1 ? "usually takes" : "usually take";
  return `${photoCountLabel(photoCount)} ${verb} ${estimatedRenderLabel(photoCount)}.`;
}
