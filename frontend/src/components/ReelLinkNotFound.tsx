import { SearchX } from "lucide-react";
import { Button } from "./ui/button";

/**
 * What a reel link that leads nowhere looks like.
 *
 * Reached two ways, and it has to read the same from both: a hash whose id
 * cannot be a real one (caught before any request goes out, see
 * `lib/hash-route.ts`), and a well-formed id the server has no reel for, which
 * is how an unknown or expired link answers. Either way the visitor gets one
 * plain sentence and a way forward, never a spinner that never stops.
 */
export function ReelLinkNotFound({ onStartNew }: { onStartNew: () => void }) {
  return (
    <div className="animate-fade-up container max-w-4xl py-12 md:py-16">
      <div className="glass mx-auto max-w-md rounded-2xl p-8 text-center">
        <span className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-white/[0.06] text-zinc-300">
          <SearchX className="h-6 w-6" />
        </span>
        <h1 className="mt-4 font-display text-2xl font-semibold text-zinc-50">
          We couldn’t find that reel
        </h1>
        <p className="mt-3 text-sm text-zinc-400">
          This link doesn’t lead to a reel we can show. It may be mistyped, or
          the reel may no longer be available. You can make a new one now.
        </p>
        {/* min-h-11: a full 44px tap target on a 375px screen, the only
            control on this screen. */}
        <Button className="mt-6 min-h-11 w-full sm:w-auto" onClick={onStartNew}>
          Start a new reel
        </Button>
      </div>
    </div>
  );
}
