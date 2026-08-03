import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { Hero } from "./components/Hero";
import { HowItWorks } from "./components/HowItWorks";
import { Studio } from "./components/Studio";
import { MyReels } from "./components/MyReels";
import { ReelLinkNotFound } from "./components/ReelLinkNotFound";
import { useReelStore } from "./store/useReelStore";
import { generateSamplePhotos, samplePhotoAlts } from "./lib/sample-photos";
import { parseHashRoute } from "./lib/hash-route";

export default function App() {
  const [started, setStarted] = useState(false);
  /** A reel named by the address bar that we should reopen instead of
   *  starting blank. Null on every ordinary visit. */
  const [resumeJobId, setResumeJobId] = useState<string | null>(null);
  /** The address bar names a reel whose id cannot be real. Answered on the
   *  spot, with no request. */
  const [brokenLink, setBrokenLink] = useState(false);
  // Only ever set true from the header's signed-in "My reels" menu item,
  // which itself renders nothing without Firebase config — so a guest build
  // (every build today) never has any control that could flip this, and this
  // branch of the render below is dead code for guest, not just untriggered.
  const [libraryOpen, setLibraryOpen] = useState(false);
  const reset = useReelStore((s) => s.reset);
  const addPhotos = useReelStore((s) => s.addPhotos);
  const goTo = useReelStore((s) => s.goTo);

  const start = () => {
    reset();
    setResumeJobId(null);
    setBrokenLink(false);
    setStarted(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Zero-friction demo path from the landing: paint the sample set, then enter
  // the studio already holding the storyboard. If canvas is unavailable we
  // still enter the studio (the upload step's own button can retry).
  const startWithSamples = async () => {
    let files: File[] = [];
    try {
      files = await generateSamplePhotos();
    } catch {
      /* fall through — enter empty */
    }
    reset();
    setResumeJobId(null);
    setBrokenLink(false);
    if (files.length > 0) addPhotos(files, samplePhotoAlts());
    setStarted(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // The address bar decides what this visit opens (see lib/hash-route.ts):
  //   #create      -> straight into the studio, as it always did
  //   #reel/<id>   -> reopen that reel, whether it is still being made or was
  //                   finished days ago. This is what makes a refresh, an
  //                   accidental close, or coming back tomorrow safe.
  //   #reel/<junk> -> say so at once, without asking the server about an id
  //                   that cannot exist
  // Anything else, including the skip link's own #main-content, is not a route
  // and lands on the normal landing page.
  //
  // Applied on load AND on every later hash change. The listener is not
  // decoration: pasting a reel link into a tab that already has this app open
  // changes only the fragment, so the browser fires `hashchange` and navigates
  // nothing. Without this the pasted link sat there doing nothing until the
  // visitor thought to reload, which is the opposite of the point.
  useEffect(() => {
    const apply = () => {
      const route = parseHashRoute(window.location.hash);
      if (route.kind === "create") {
        setStarted(true);
      } else if (route.kind === "reel") {
        setResumeJobId(route.jobId);
        setBrokenLink(false);
        goTo("generate");
        setStarted(true);
      } else if (route.kind === "broken") {
        setResumeJobId(null);
        setBrokenLink(true);
      }
      // `none` is deliberately inert: the skip link sets #main-content on
      // every keyboard visitor, and clearing the reel we are watching because
      // someone pressed Tab would be an unpleasant surprise.
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [goTo]);

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
      <Header
        onOpenLibrary={() => {
          setLibraryOpen(true);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />
      <main id="main-content" className="flex-1">
        {libraryOpen ? (
          <MyReels onBack={() => setLibraryOpen(false)} />
        ) : brokenLink ? (
          <ReelLinkNotFound onStartNew={start} />
        ) : started ? (
          <Studio resumeJobId={resumeJobId} onStartNew={start} />
        ) : (
          <>
            <Hero onStart={start} onTrySamples={startWithSamples} />
            <HowItWorks />
          </>
        )}
      </main>
      <Footer />
    </div>
  );
}
