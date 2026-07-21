import { useEffect, useState } from "react";

/** How long each photo holds the frame before crossfading to the next. */
const SLIDE_MS = 5200;

/**
 * Client-side Ken Burns slideshow for the letterbox when there is no playable
 * video (offline generator / degraded run): the user's own photos slowly
 * zoom-pan and crossfade, so the money screen never looks dead.
 *
 * Motion a11y: the zoom/pan transform is disabled under
 * `prefers-reduced-motion: reduce` (see index.css — the `.kb-pan-*` animations
 * are zeroed out); the slow opacity crossfade remains, as fades are not
 * vestibular-triggering motion.
 */
export function KenBurnsSlideshow({ photos }: { photos: Array<{ url: string; name: string }> }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (photos.length < 2) return;
    const id = window.setInterval(
      () => setActive((a) => (a + 1) % photos.length),
      SLIDE_MS,
    );
    return () => window.clearInterval(id);
  }, [photos.length]);

  return (
    <div
      role="img"
      aria-label={`Slideshow of your ${photos.length} uploaded ${photos.length === 1 ? "photo" : "photos"}`}
      data-testid="kenburns-slideshow"
      className="absolute inset-0 overflow-hidden"
    >
      {photos.map((p, i) => (
        <img
          key={p.url}
          src={p.url}
          alt=""
          aria-hidden
          draggable={false}
          className={`kb-slide ${i % 2 === 0 ? "kb-pan-a" : "kb-pan-b"} ${
            i === active ? "kb-slide-active" : ""
          }`}
        />
      ))}
      {/* Gentle grade so overlaid chips/captions stay readable on any photo. */}
      <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-ink-950/60 via-transparent to-ink-950/40" />
    </div>
  );
}
