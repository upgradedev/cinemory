/**
 * The time budget of one reel, and the photo cap that has to fit inside it.
 *
 * Every number here is measured on the deployed service, and the check that
 * the cap fits is arithmetic rather than hope — so if the ceiling, the
 * measurement or the cap moves, a test says so instead of a visitor finding
 * out by waiting.
 *
 * Generation calls now run CONCURRENTLY, up to
 * `MAX_CONCURRENT_GENERATIONS` at once (see `cinemory.pipeline`). The calls
 * were always independent: one photo in, one clip out, and a chapter bridge is
 * generated from neighbouring PHOTOS rather than from a generated clip.
 * Running them one after another was costing the full sum of their latencies
 * for no reason. So the cost of a reel is the number of WAVES, not the number
 * of photos:
 *
 *   waves(n) = ceil(n / 5)
 *   seconds  = waves x 314 + 45
 *
 * At the cap of 5 photos that is one wave: 314 + 45 = 359 s, about 6 minutes,
 * against a 720 s ceiling. Sequentially the same reel would have been
 * 5 x 314 + 45 = 1615 s, about 27 minutes, which is why 5 photos could never
 * finish before this.
 *
 * Measured, live, on the deployed service (2026-08-03), sequentially:
 *   1 photo  -> 325 s end to end
 *   2 photos -> 626 s end to end
 * so ~310 s per generation call and ~15 s of fixed overhead. The 314 s and
 * 45 s below are both the conservative side of those measurements.
 *
 * The cap itself is a product decision (5 photos), not an output of this
 * arithmetic: the window would allow more. It is a property of THIS demo, not
 * of the reel maker, which accepts up to 60 photos server-side
 * (`cinemory.ingest`). The UI says so in those words rather than implying a
 * product limit.
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
 * seconds. Measured on the deployed service, 2026-08-03: a 1-photo run took
 * 325 s end to end and a 2-photo sequential run took 626 s, so a call is
 * ~310 s and this is rounded up.
 */
export const LIVE_SECONDS_PER_PHOTO = 314;

/**
 * How many generation calls the backend runs at once
 * (`cinemory.pipeline.MAX_CONCURRENT_GENERATIONS`). Mirrored here because the
 * estimate a visitor reads has to match what the server actually does; the two
 * are pinned together by a contract test.
 *
 * Set to the photo cap, so one reel is one wave. Deliberately conservative:
 * the provider's real concurrency limit is not published to us, so this is a
 * chosen small number rather than a tuned one, and a rate-limited call backs
 * off and retries instead of failing.
 */
export const MAX_CONCURRENT_GENERATIONS = 5;

/**
 * Everything in a run that is not per-photo generation: sending the photos up,
 * hosting them for the model to read, stitching the clips, writing every
 * artifact to storage, and sealing the manifest. Held back from the generation
 * budget so the cap has real headroom rather than exactly filling the window.
 */
export const RUN_OVERHEAD_SECONDS = 45;

/**
 * The most photos one reel can hold here.
 *
 * A product decision, not an output of the arithmetic above: the waiting
 * window would allow more than this at the current concurrency. What the
 * arithmetic must do is CHECK it, which is what `capFitsTheWindow` below is
 * for and what a test asserts.
 */
export const MAX_REEL_PHOTOS = 5;

/** How many concurrent waves of generation `photoCount` photos take. */
export function renderWaves(photoCount: number): number {
  return Math.ceil(Math.max(1, photoCount) / MAX_CONCURRENT_GENERATIONS);
}

/** Expected wall clock, in seconds, for a reel made from `photoCount` photos. */
export function estimatedRenderSeconds(photoCount: number): number {
  const n = Math.min(Math.max(Math.floor(photoCount) || 0, 1), MAX_REEL_PHOTOS);
  return renderWaves(n) * LIVE_SECONDS_PER_PHOTO + RUN_OVERHEAD_SECONDS;
}

/**
 * Whether a full reel still finishes inside the window the app is willing to
 * wait. The guard on the cap being a decision rather than a derivation: if
 * someone raises the cap, lowers the concurrency, or the measurement gets
 * worse, this goes false and the test that reads it fails.
 */
export function capFitsTheWindow(): boolean {
  return estimatedRenderSeconds(MAX_REEL_PHOTOS) < REEL_JOB_MAX_POLL_MS / 1000;
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
