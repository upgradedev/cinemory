/**
 * The address bar as app state, with no router library.
 *
 * A reel takes minutes to make. Before this module the whole in-flight run
 * lived in one tab's memory, so a refresh, an accidental close, or a browser
 * reload threw it away even though the work carried on server-side and
 * `GET /reels/jobs/{id}` could still be read. Putting the id in the URL makes
 * the page resumable: the same link reopens the run in progress, and once the
 * run is finished it reopens the finished reel, today or tomorrow, because the
 * job's stored status keeps its sealed result (see `cinemory.jobs`).
 *
 * Shape: `#reel/<id>`. The app already used `window.location.hash` for
 * `#create` and pulls in no router, so a hash route stays dependency-free.
 * "reel" rather than "job" because this is a visitor's address bar, and a reel
 * is what they think they have a link to.
 *
 * Every parse is total: an id that is unknown, expired or malformed resolves
 * to a state the app can render as one plain "we couldn't find that reel"
 * screen, never a spinner that never stops and never a broken page. Malformed
 * is caught HERE, before any request goes out, so a junk link answers instantly.
 */

/** The prefix that marks a hash as naming a reel. */
export const REEL_HASH_PREFIX = "#reel/";

/**
 * What a well-formed id may look like. Job ids are
 * `secrets.token_urlsafe(18)` server-side (24 chars of `[A-Za-z0-9_-]`); this
 * is deliberately much wider than that exact shape. The asymmetry matters: a
 * floor that is too loose costs one pointless 404 round trip, while a floor
 * that is too tight refuses a link that would have worked. So this rejects
 * only what cannot be an id at all (empty, wrong alphabet, absurd length) and
 * lets the server be the authority on everything else.
 */
const REEL_ID_PATTERN = /^[A-Za-z0-9_-]{4,128}$/;

export type HashRoute =
  /** No hash, or a hash this app does not route on (e.g. `#main-content`). */
  | { kind: "none" }
  /** `#create` — jump straight into the studio. Predates this module. */
  | { kind: "create" }
  /** `#reel/<id>` with a plausible id: resume it. */
  | { kind: "reel"; jobId: string }
  /** `#reel/...` with an id that cannot be one: say so, do not request it. */
  | { kind: "broken" };

/** Read a `window.location.hash` value as a route. Never throws. */
export function parseHashRoute(hash: string): HashRoute {
  if (!hash || hash === "#") return { kind: "none" };
  const normalised = hash.startsWith("#") ? hash : `#${hash}`;
  if (normalised === "#create") return { kind: "create" };
  if (!normalised.startsWith(REEL_HASH_PREFIX)) return { kind: "none" };

  const raw = normalised.slice(REEL_HASH_PREFIX.length);
  let jobId: string;
  try {
    jobId = decodeURIComponent(raw);
  } catch {
    // A stray "%" makes decodeURIComponent throw. That is a broken link, not
    // a crash.
    return { kind: "broken" };
  }
  return REEL_ID_PATTERN.test(jobId) ? { kind: "reel", jobId } : { kind: "broken" };
}

/** The hash that names a given reel. */
export function reelHash(jobId: string): string {
  return `${REEL_HASH_PREFIX}${encodeURIComponent(jobId)}`;
}

/**
 * Point the address bar at this reel.
 *
 * `history.replaceState`, not an assignment to `location.hash`: assigning
 * pushes a history entry, so Back would walk through every reel the visitor
 * started in this tab instead of leaving the page. Replacing keeps Back
 * meaning "leave", while the link in the bar stays copyable and survives a
 * refresh, which is the whole point.
 */
export function rememberReel(jobId: string): void {
  if (typeof window === "undefined") return;
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}${reelHash(jobId)}`);
}

/** Drop any reel from the address bar, so a refresh starts clean. */
export function forgetReel(): void {
  if (typeof window === "undefined") return;
  if (!window.location.hash) return;
  const { pathname, search } = window.location;
  window.history.replaceState(null, "", `${pathname}${search}`);
}
