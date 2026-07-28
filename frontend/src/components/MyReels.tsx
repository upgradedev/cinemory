import { useEffect, useRef, useState } from "react";
import { ArrowLeft, FolderOpen, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { HashChip } from "./HashChip";
import { ConfirmDialog } from "./ConfirmDialog";
import { useAuthUser } from "@/lib/auth";
import { ApiError, type LibraryReel } from "@/lib/api";
import { useDeleteMyData, useManifest, useMyLibrary } from "@/lib/queries";

function formatDate(iso: string | null): string {
  if (!iso) return "Date unknown";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Date unknown";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** The signed-in tenant's own reel library — only ever mounted from the
 *  header's account menu, which itself only renders "My reels" when a user
 *  is signed in. Still defends against a client-side sign-out happening
 *  WHILE this view is open (the header stays mounted and reachable): once
 *  the auth state has definitively resolved to signed-out (not just still
 *  loading), it hands control back via `onBack` rather than keep showing a
 *  stale library. */
export function MyReels({ onBack }: { onBack: () => void }) {
  const { user, loading } = useAuthUser();
  const library = useMyLibrary(user !== null);
  const deleteAll = useDeleteMyData();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [justDeleted, setJustDeleted] = useState(false);
  const dismissTimer = useRef<number | null>(null);

  useEffect(() => {
    if (!loading && user === null) onBack();
  }, [loading, user, onBack]);

  useEffect(
    () => () => {
      if (dismissTimer.current !== null) window.clearTimeout(dismissTimer.current);
    },
    [],
  );

  const unavailable =
    library.isError && library.error instanceof ApiError && library.error.status === 401;

  const handleDelete = () => {
    deleteAll.mutate(undefined, {
      onSuccess: () => {
        setConfirmOpen(false);
        setJustDeleted(true);
        if (dismissTimer.current !== null) window.clearTimeout(dismissTimer.current);
        dismissTimer.current = window.setTimeout(() => setJustDeleted(false), 4000);
      },
    });
  };

  return (
    <section className="container max-w-3xl py-12 md:py-16">
      <button
        type="button"
        onClick={onBack}
        className="mb-6 inline-flex min-h-11 items-center gap-1.5 text-sm text-zinc-400 transition-colors hover:text-zinc-200 sm:min-h-0"
      >
        <ArrowLeft className="h-4 w-4" />
        Back
      </button>

      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-zinc-50">My reels</h1>
          <p className="mt-2 text-zinc-400">Every reel saved to your account.</p>
        </div>
        {!!library.data?.length && (
          <Button variant="destructive" size="sm" onClick={() => setConfirmOpen(true)}>
            <Trash2 className="h-4 w-4" />
            Delete all my data
          </Button>
        )}
      </div>

      {justDeleted && (
        <p
          role="status"
          className="mb-6 rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4 text-sm text-emerald-300"
        >
          All your data has been deleted.
        </p>
      )}

      {library.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-xl border border-white/[0.06] bg-ink-900/50"
            />
          ))}
        </div>
      )}

      {unavailable && (
        <p className="rounded-xl border border-white/[0.06] bg-ink-900/50 p-4 text-sm text-zinc-400">
          Sign-in library is not available on this deployment.
        </p>
      )}

      {library.isError && !unavailable && (
        <p className="rounded-xl border border-white/[0.06] bg-ink-900/50 p-4 text-sm text-zinc-400">
          Could not load your reels right now. Try again in a moment.
        </p>
      )}

      {library.data?.length === 0 && (
        <div className="rounded-xl border border-white/[0.06] bg-ink-900/50 p-8 text-center">
          <FolderOpen className="mx-auto h-8 w-8 text-zinc-500" aria-hidden />
          <p className="mt-3 text-sm text-zinc-400">You have not saved any reels yet.</p>
        </div>
      )}

      {!!library.data?.length && (
        <ul className="space-y-3">
          {library.data.map((reel) => (
            <ReelRow key={reel.reel_name} reel={reel} />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={confirmOpen}
        title="Delete all your data?"
        description="This permanently deletes every reel linked to your account. This cannot be undone."
        confirmLabel="Delete everything"
        destructive
        busy={deleteAll.isPending}
        error={deleteAll.isError ? "Could not delete your data right now. Try again." : null}
        onConfirm={handleDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </section>
  );
}

function ReelRow({ reel }: { reel: LibraryReel }) {
  const [expanded, setExpanded] = useState(false);
  const manifest = useManifest(expanded ? reel.reel_name : null);
  // A reel name can contain spaces or other characters that are not valid in
  // an HTML id token, so it's sanitized before use — id and aria-controls
  // just need to agree with each other, not preserve the raw name.
  const panelId = `provenance-${reel.reel_name.replace(/[^a-zA-Z0-9_-]/g, "-")}`;

  return (
    <li className="rounded-xl border border-white/[0.06] bg-ink-900/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-zinc-100">{reel.reel_name}</p>
          <p className="text-xs text-zinc-400">{formatDate(reel.created_at)}</p>
        </div>
        <div className="flex items-center gap-2">
          {reel.manifest_hash && <HashChip hash={reel.manifest_hash} label="manifest_hash" />}
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Hide provenance" : "View provenance"}
          </Button>
        </div>
      </div>

      {expanded && (
        <div id={panelId} className="mt-4 border-t border-white/[0.06] pt-4">
          {manifest.isLoading && (
            <p className="flex items-center gap-2 text-xs text-zinc-400">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              Loading provenance…
            </p>
          )}
          {manifest.isError && (
            <p className="text-xs text-zinc-400">Could not load this reel's details right now.</p>
          )}
          {manifest.data && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
              <Badge variant="neutral">{manifest.data.occasion}</Badge>
              <Badge variant="neutral">{manifest.data.steps.length} generative steps</Badge>
              <HashChip hash={manifest.data.reel_asset.sha256} label="reel_sha256" />
              <span className="inline-flex items-center gap-1 text-emerald-400">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                Sealed
              </span>
            </div>
          )}
          {!manifest.isLoading && !manifest.isError && !manifest.data && (
            <p className="text-xs text-zinc-400">
              Full provenance for this reel is not available on this deployment.
            </p>
          )}
        </div>
      )}
    </li>
  );
}
