import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { Studio } from "./components/Studio";
import { useReelStore } from "./store/useReelStore";

export default function App() {
  const [started, setStarted] = useState(false);
  const reset = useReelStore((s) => s.reset);

  const start = () => {
    reset();
    setStarted(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Deep-link: /#create jumps straight into the studio.
  useEffect(() => {
    if (window.location.hash === "#create") setStarted(true);
  }, []);

  return (
    <div className="film-grain flex min-h-dvh flex-col">
      {/* Keyboard-first: a hidden skip link that reveals on focus and jumps
          past the header straight to the main content. */}
      <a
        href="#main-content"
        className="sr-only rounded-lg bg-gold-400 px-4 py-2 text-sm font-semibold text-ink-950 focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:inline-flex focus:items-center"
      >
        Skip to content
      </a>
      <Header />
      <main id="main-content" className="flex-1">
        {started ? <Studio /> : <Hero onStart={start} />}
      </main>
      <Footer />
    </div>
  );
}
