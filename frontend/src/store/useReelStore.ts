import { create } from "zustand";
import { MAX_REEL_PHOTOS } from "@/lib/reel-budget";
import { forgetReel } from "@/lib/hash-route";

export type Step = "upload" | "occasion" | "generate" | "result";

export interface LocalPhoto {
  id: string;
  file: File;
  url: string; // object URL for the thumbnail preview
  name: string;
  /** Descriptive alt text for the thumbnail (defaults to the filename). */
  alt: string;
}

interface ReelState {
  step: Step;
  photos: LocalPhoto[];
  occasionKey: string | null;
  /**
   * How many images the MOST RECENT `addPhotos` had to leave out because the
   * reel is already at `MAX_REEL_PHOTOS`. Zero when nothing was left out.
   *
   * The cap is enforced here, at the one place photos enter the app, so no
   * caller can forget it. It is recorded rather than applied silently: a
   * selection that gets quietly shortened is the kind of thing someone only
   * discovers in the finished reel, so the upload step reads this and says
   * plainly what was dropped.
   */
  overflow: number;

  goTo: (step: Step) => void;
  addPhotos: (files: File[], alts?: string[]) => void;
  removePhoto: (id: string) => void;
  reorderPhotos: (fromId: string, toId: string) => void;
  clearPhotos: () => void;
  setOccasion: (key: string) => void;
  reset: () => void;
}

let counter = 0;
const uid = () => `p_${Date.now().toString(36)}_${(counter += 1)}`;

const ACCEPTED = /^image\//;

export const useReelStore = create<ReelState>((set, get) => ({
  step: "upload",
  photos: [],
  occasionKey: null,
  overflow: 0,

  goTo: (step) => set({ step }),

  addPhotos: (files, alts) =>
    set((state) => {
      // Pair alt text with each file BEFORE filtering so alignment survives a
      // dropped non-image; alt falls back to the filename.
      const images = files
        .map((file, i) => ({ file, alt: alts?.[i] }))
        .filter(({ file }) => ACCEPTED.test(file.type));
      // Only IMAGES count toward the cap and toward `overflow`: a dropped
      // non-image was never a candidate photo, so reporting it as "left out
      // because the reel is full" would be a lie.
      const room = Math.max(0, MAX_REEL_PHOTOS - state.photos.length);
      const accepted = images.slice(0, room);
      const next = accepted.map<LocalPhoto>(({ file, alt }) => ({
        id: uid(),
        file,
        url: URL.createObjectURL(file),
        name: file.name,
        alt: alt ?? file.name,
      }));
      return {
        photos: [...state.photos, ...next],
        overflow: images.length - accepted.length,
      };
    }),

  removePhoto: (id) =>
    set((state) => {
      const target = state.photos.find((p) => p.id === id);
      if (target) URL.revokeObjectURL(target.url);
      // Making room again retires the "we left some out" note: it described
      // one specific add, and that add is no longer what is on screen.
      return { photos: state.photos.filter((p) => p.id !== id), overflow: 0 };
    }),

  reorderPhotos: (fromId, toId) =>
    set((state) => {
      const photos = [...state.photos];
      const from = photos.findIndex((p) => p.id === fromId);
      const to = photos.findIndex((p) => p.id === toId);
      if (from === -1 || to === -1 || from === to) return {};
      const [moved] = photos.splice(from, 1);
      photos.splice(to, 0, moved as LocalPhoto);
      return { photos };
    }),

  clearPhotos: () => {
    get().photos.forEach((p) => URL.revokeObjectURL(p.url));
    set({ photos: [], overflow: 0 });
  },

  setOccasion: (key) => set({ occasionKey: key }),

  reset: () => {
    get().photos.forEach((p) => URL.revokeObjectURL(p.url));
    // Throwing away the current reel throws away its link too, otherwise a
    // refresh right after "Create another reel" would silently reopen the reel
    // that was just abandoned. This lives here, in the one function that means
    // "start over", rather than at each of its call sites, where it could be
    // forgotten by the next one added.
    forgetReel();
    set({ step: "upload", photos: [], occasionKey: null, overflow: 0 });
  },
}));

/**
 * Derive the reel's chapter structure from the selected photo count.
 *
 * When photos are selected, their real bytes are submitted as a background
 * job (`POST /reels/jobs`, polled via `GET /reels/jobs/{id}` — see
 * usePollReelJob) and only `chapters` shapes the edit (the server groups the
 * uploaded photos across chapters). With no photos selected we fall back to
 * the synthetic `POST /reels` path, which composes a reel from
 * `chapters × per_chapter` scenes. Either way photos are grouped into 2–5
 * chapters, so a larger memory set yields a richer, longer reel.
 */
export function deriveReelShape(photoCount: number): {
  chapters: number;
  per_chapter: number;
} {
  const n = Math.max(photoCount, 1);
  const chapters = Math.min(5, Math.max(2, Math.ceil(Math.sqrt(n))));
  const per_chapter = Math.max(1, Math.min(4, Math.ceil(n / chapters)));
  return { chapters, per_chapter };
}
