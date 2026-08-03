/**
 * Turning "the live model failed" into a sentence a visitor can act on.
 *
 * The app already degraded honestly when a live generation failed: it remade
 * the reel with the built-in fallback, said so on screen, and sealed that fact
 * into the manifest. What it did not say was WHY. When the generation account
 * ran out of credit, the visitor saw only "this is taking longer than
 * expected" and the owner had to read the server logs to find out what had
 * actually happened.
 *
 * So the backend now classifies each live failure into one coarse category
 * (`degrade_kind`, see `cinemory.api._degrade_kind`) and this module maps that
 * category to plain language. The category is the ONLY thing that crosses the
 * wire: no provider name, no credentials, no upstream response text, no
 * exception message. The full detail stays in the server log, where an
 * operator can find it and a browser cannot.
 *
 * An unrecognised or absent category is not an error here. It falls back to
 * the honest general sentence, so an older backend, a newer category, or a
 * failure nobody has classified yet still reads as a complete explanation
 * rather than a blank.
 */

/** The categories the backend currently emits. */
export type DegradeKind =
  | "credit"
  | "busy"
  | "timeout"
  | "unavailable"
  | "refused"
  | "unknown";

const CAUSE: Record<DegradeKind, string> = {
  credit: "The live model could not run because our generation credit ran out.",
  busy: "The live model was busy and could not take this run.",
  timeout: "The live model took too long to answer.",
  unavailable: "The live model could not be reached.",
  refused: "The live model turned this run down.",
  unknown: "The live model was unavailable.",
};

/** What every degraded run is true of, whatever caused it. */
const CONSEQUENCE =
  "This reel was made with the built-in fallback instead, and it is labelled as such. Storage and provenance are real.";

/** The one-line cause, for a tight space. */
export function degradeCause(kind?: string | null): string {
  return CAUSE[(kind ?? "") as DegradeKind] ?? CAUSE.unknown;
}

/** Cause plus consequence: the full explanation a visitor reads. */
export function degradeNote(kind?: string | null): string {
  return `${degradeCause(kind)} ${CONSEQUENCE}`;
}
