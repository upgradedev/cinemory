import { ShieldCheck } from "lucide-react";

export function Footer() {
  return (
    <footer className="border-t border-white/[0.05] py-10">
      <div className="container flex flex-col items-center justify-between gap-4 text-sm text-zinc-500 sm:flex-row">
        <p>
          © {new Date().getFullYear()} Cinemory · cinemory.ai — your memories,
          made into film.
        </p>
        <p className="inline-flex items-center gap-1.5">
          <ShieldCheck className="h-4 w-4 text-emerald-400/70" />
          Every reel is provenance-sealed on Backblaze B2.
        </p>
      </div>
    </footer>
  );
}
