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
      <Header />
      <main className="flex-1">
        {started ? <Studio /> : <Hero onStart={start} />}
      </main>
      <Footer />
    </div>
  );
}
