import { create } from "zustand";

export type Step = "upload" | "occasion" | "generate" | "result";

export interface LocalPhoto {
  id: string;
  file: File;
  url: string; // object URL for the thumbnail preview
  name: string;
}

interface ReelState {
  step: Step;
  photos: LocalPhoto[];
  occasionKey: string | null;

  goTo: (step: Step) => void;
  addPhotos: (files: File[]) => void;
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

  goTo: (step) => set({ step }),

  addPhotos: (files) =>
    set((state) => {
      const next = files
        .filter((f) => ACCEPTED.test(f.type))
        .map<LocalPhoto>((file) => ({
          id: uid(),
          file,
          url: URL.createObjectURL(file),
          name: file.name,
        }));
      return { photos: [...state.photos, ...next] };
    }),

  removePhoto: (id) =>
    set((state) => {
      const target = state.photos.find((p) => p.id === id);
      if (target) URL.revokeObjectURL(target.url);
      return { photos: state.photos.filter((p) => p.id !== id) };
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
    set({ photos: [] });
  },

  setOccasion: (key) => set({ occasionKey: key }),

  reset: () => {
    get().photos.forEach((p) => URL.revokeObjectURL(p.url));
    set({ step: "upload", photos: [], occasionKey: null });
  },
}));

/**
 * Map the local photo set onto the backend's synthetic reel spec.
 *
 * `POST /reels` takes no image bytes — it composes a reel from
 * `chapters × per_chapter` scenes. We honour the user's selection by shaping
 * the reel structure from the photo count: photos are grouped into 2–5
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
