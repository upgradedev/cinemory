import { Github, ShieldCheck } from "lucide-react";

export function Footer() {
  return (
    <footer className="border-t border-white/[0.05] py-10">
      <div className="container flex flex-col items-center gap-4 text-sm text-zinc-400 sm:flex-row sm:justify-between">
        <p>© {new Date().getFullYear()} Cinemory — your memories, made into film.</p>
        {/* The repo link is a standalone control (not buried mid-sentence) so it
            is a real >=44px tap target on touch, tightening on >=sm. */}
        <div className="flex flex-col items-center gap-3 sm:flex-row sm:gap-5">
          <a
            href="https://github.com/upgradedev/cinemory"
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg underline decoration-white/20 underline-offset-2 transition-colors hover:text-zinc-200 sm:min-h-0"
          >
            <Github className="h-4 w-4" aria-hidden />
            github.com/upgradedev/cinemory
          </a>
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="h-4 w-4 text-emerald-400/70" aria-hidden />
            Every reel is sealed with verifiable SHA-256 provenance.
          </span>
        </div>
      </div>
    </footer>
  );
}
