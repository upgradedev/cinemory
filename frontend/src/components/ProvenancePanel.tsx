import { useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  Database,
  FileCheck2,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { HashChip } from "./HashChip";
import { useManifest } from "@/lib/queries";
import {
  fetchReelReceipt,
  verifyReelProvenance,
  type ProvenanceVerification,
  type ReceiptState,
} from "@/lib/provenance-verify";
import type { ReelResponse } from "@/lib/api";
import { formatBytes } from "@/lib/utils";

const MODALITY_ICON: Record<string, string> = {
  image: "🖼️",
  video: "🎞️",
  audio: "🎵",
  text: "📝",
};

type VerifyUiState = { phase: "idle" | "verifying" } | (ProvenanceVerification & { phase: "done" });
type ReceiptUiState = { phase: "idle" | "verifying" } | (ReceiptState & { phase: "done" });

export function ProvenancePanel({ reel }: { reel: ReelResponse }) {
  const { data: manifest, isLoading } = useManifest(reel.reel_name);
  const [verify, setVerify] = useState<VerifyUiState>({ phase: "idle" });
  const [receipt, setReceipt] = useState<ReceiptUiState>({ phase: "idle" });

  const onVerify = async () => {
    setVerify({ phase: "verifying" });
    setReceipt({ phase: "verifying" });
    // Two independent, complementary checks run in parallel: the in-browser seal
    // recompute (proves the manifest bytes are intact) and the server-side
    // named-check receipt (re-hashes every stored artifact + structural checks).
    const [seal, rec] = await Promise.all([
      verifyReelProvenance(reel.reel_name, reel.manifest_hash),
      fetchReelReceipt(reel.reel_name),
    ]);
    setVerify({ phase: "done", ...seal });
    setReceipt({ phase: "done", ...rec });
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      aria-labelledby="provenance-heading"
      // overflow-hidden contains long unbreakable hashes/URIs/model names: their
      // truncated text boxes still extend past the panel and would otherwise add
      // phantom horizontal page scroll on mobile.
      className="overflow-hidden rounded-2xl border border-white/[0.06] bg-ink-800/60 p-6 shadow-film"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h2
              id="provenance-heading"
              className="font-display text-xl font-semibold text-zinc-50"
            >
              Provenance
            </h2>
          </div>
          <p className="mt-1 text-sm text-zinc-400">
            Every asset is content-addressed by SHA-256 and the manifest is
            sealed — tampering with any field breaks the hash.
          </p>
        </div>
        <SealBadge verify={verify} />
      </div>

      {/* Manifest seal + storage */}
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="min-w-0 rounded-xl border border-white/[0.06] bg-ink-900/50 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-400">
            Manifest seal
          </p>
          <div className="mt-2">
            <HashChip hash={reel.manifest_hash} label="manifest_hash" />
          </div>
          {reel.manifest_uri && (
            <p className="mt-2 truncate font-mono text-[11px] text-zinc-400">
              {reel.manifest_uri}
            </p>
          )}
          <div className="mt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={onVerify}
              disabled={verify.phase === "verifying"}
              aria-describedby="verify-outcome"
            >
              {verify.phase === "verifying" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <BadgeCheck className="h-3.5 w-3.5" />
              )}
              {verify.phase === "done" ? "Re-verify provenance" : "Verify provenance"}
            </Button>
            <p
              id="verify-outcome"
              role="status"
              aria-live="polite"
              className={
                verify.phase === "done" && verify.state === "failed"
                  ? "mt-2 text-xs text-red-400"
                  : "mt-2 text-xs text-zinc-400"
              }
            >
              {verify.phase === "done"
                ? verify.detail
                : verify.phase === "verifying"
                  ? "Re-fetching the manifest and recomputing its SHA-256 in your browser…"
                  : "Re-fetch the manifest and recompute its SHA-256 right here, in your browser."}
            </p>
          </div>
        </div>
        <div className="min-w-0 rounded-xl border border-white/[0.06] bg-ink-900/50 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-400">Storage</p>
          <div className="mt-2 flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-ember-500/15 text-ember-400">
              <Database className="h-3.5 w-3.5" />
            </span>
            <span className="text-sm font-medium text-zinc-200">
              Backblaze B2
            </span>
          </div>
          <p className="mt-2 truncate font-mono text-[11px] text-zinc-400">
            {reel.reel_url ?? "—"}
          </p>
        </div>
      </div>

      {/* Reel asset hash */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-white/[0.06] bg-ink-900/50 p-4">
        <span className="text-xs uppercase tracking-wide text-zinc-400">
          Reel asset
        </span>
        <HashChip hash={reel.reel_sha256} label="reel_sha256" />
        <Badge variant="neutral">{reel.steps} generative steps</Badge>
      </div>

      {/* Server-side aggregate re-verification (named checks re-run from the
          stored bytes), shown after the visitor clicks Verify. */}
      <ServerRecheck receipt={receipt} />

      {/* Per-step provenance (from the sealed manifest) */}
      <div className="mt-5">
        <p className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
          Genblaze pipeline steps
        </p>

        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-12 animate-pulse rounded-lg border border-white/[0.06] bg-ink-900/50"
              />
            ))}
          </div>
        )}

        {manifest ? (
          <ol className="space-y-2">
            {manifest.steps.map((step, i) => (
              <li
                key={`${step.provider}-${i}`}
                className="flex items-center gap-3 rounded-lg border border-white/[0.06] bg-ink-900/50 p-3"
              >
                <span className="text-lg" aria-hidden>
                  {MODALITY_ICON[step.modality] ?? "•"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-zinc-200">
                    <span className="font-medium">{step.provider}</span>
                    <span className="text-zinc-400"> · {step.model}</span>
                  </p>
                  <p className="truncate text-xs text-zinc-400">{step.prompt}</p>
                </div>
                <div className="hidden text-right sm:block">
                  <span className="text-[11px] text-zinc-400">
                    {formatBytes(step.asset.size_bytes)}
                  </span>
                </div>
                <HashChip hash={step.asset.sha256} />
              </li>
            ))}
          </ol>
        ) : (
          !isLoading && (
            <p className="rounded-lg border border-white/[0.06] bg-ink-900/50 p-3 text-xs text-zinc-400">
              Full step manifest is available on the offline/indexed store. On the
              live B2 path the {reel.steps}-step provenance is sealed inside the
              reel container and verified on download.
            </p>
          )
        )}
      </div>
    </motion.section>
  );
}

/** The seal badge next to the heading: "Sealed" at rest, then the live
 *  verification outcome — "Verified ✓" (subtle pop), red "Verification
 *  failed", or a muted "Can't verify here" when the manifest isn't fetchable. */
function SealBadge({ verify }: { verify: VerifyUiState }) {
  if (verify.phase === "verifying") {
    return (
      <Badge variant="neutral">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Verifying…
      </Badge>
    );
  }
  if (verify.phase === "done") {
    if (verify.state === "verified") {
      return (
        <motion.span
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 16 }}
        >
          <Badge variant="verified">
            <ShieldCheck className="h-3.5 w-3.5" />
            Verified ✓
          </Badge>
        </motion.span>
      );
    }
    if (verify.state === "failed") {
      return (
        <Badge
          variant="neutral"
          className="border-red-400/40 bg-red-500/10 text-red-300"
        >
          <ShieldAlert className="h-3.5 w-3.5" />
          Verification failed
        </Badge>
      );
    }
    return (
      <Badge variant="muted" title={verify.detail}>
        Can&apos;t verify here
      </Badge>
    );
  }
  return (
    <Badge variant="verified">
      <FileCheck2 className="h-3.5 w-3.5" />
      Sealed
    </Badge>
  );
}

/** The server-side aggregate re-verification: after Verify is clicked, the app
 *  also calls `GET /reels/{name}/verify`, which re-hashes every stored artifact
 *  and re-runs the structural checks, and renders each named check with a TEXT
 *  pass/fail label (never colour alone) plus its evidence. Honest-degrade: when
 *  the deployment doesn't serve a receipt (404) or the body isn't a well-formed
 *  receipt, it shows a muted "can't re-check here" line, never a red failure. */
function ServerRecheck({ receipt }: { receipt: ReceiptUiState }) {
  if (receipt.phase !== "done") {
    if (receipt.phase === "verifying") {
      return (
        <p role="status" aria-live="polite" className="mt-3 text-xs text-zinc-400">
          Re-verifying every stored artifact on the server…
        </p>
      );
    }
    return null; // idle — nothing to show until Verify is clicked
  }
  if (receipt.state === "unavailable") {
    return (
      <p
        role="status"
        aria-live="polite"
        className="mt-3 rounded-xl border border-white/[0.06] bg-ink-900/50 p-3 text-xs text-zinc-400"
      >
        {receipt.detail}
      </p>
    );
  }
  const { checks } = receipt.receipt;
  const passed = checks.filter((c) => c.passed).length;
  const allPassed = receipt.state === "verified";
  return (
    <div className="mt-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
        <p className="text-xs uppercase tracking-wide text-zinc-400">
          Server re-verification
        </p>
        <span
          role="status"
          aria-live="polite"
          className={
            allPassed
              ? "text-[11px] font-medium text-emerald-400"
              : "text-[11px] font-medium text-red-400"
          }
        >
          {passed}/{checks.length} checks passed
          {allPassed ? " — all verified" : " — tamper detected"}
        </span>
      </div>
      <ul className="space-y-2">
        {checks.map((c) => (
          <li
            key={c.id}
            className="flex items-start gap-3 rounded-lg border border-white/[0.06] bg-ink-900/50 p-3"
          >
            {c.passed ? (
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" aria-hidden />
            ) : (
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-400" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-sm text-zinc-200">
                <span className="sr-only">{c.passed ? "Passed" : "Failed"}: </span>
                {c.label}
              </p>
              <p className="mt-0.5 break-words text-xs text-zinc-400">{c.evidence}</p>
            </div>
            <span
              className={
                c.passed
                  ? "shrink-0 text-[11px] font-medium text-emerald-400"
                  : "shrink-0 text-[11px] font-medium text-red-400"
              }
            >
              {c.passed ? "Passed" : "Failed"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
