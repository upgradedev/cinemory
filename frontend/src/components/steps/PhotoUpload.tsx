import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, ImagePlus, Trash2, UploadCloud, X } from "lucide-react";
import { Button } from "../ui/button";
import { useReelStore } from "@/store/useReelStore";
import { cn } from "@/lib/utils";

export function PhotoUpload() {
  const photos = useReelStore((s) => s.photos);
  const addPhotos = useReelStore((s) => s.addPhotos);
  const removePhoto = useReelStore((s) => s.removePhoto);
  const reorderPhotos = useReelStore((s) => s.reorderPhotos);
  const clearPhotos = useReelStore((s) => s.clearPhotos);
  const goTo = useReelStore((s) => s.goTo);

  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);

  const onFiles = (files: FileList | null) => {
    if (files) addPhotos(Array.from(files));
  };

  return (
    <div className="animate-fade-up">
      <StepHeading
        title="Bring your memories"
        subtitle="Drop the photos you want in the reel. Reorder them to set the story — the order becomes the edit."
      />

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          onFiles(e.dataTransfer.files);
        }}
        className={cn(
          "group relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
          dragOver
            ? "border-gold-400 bg-gold-400/[0.06]"
            : "border-white/10 bg-ink-800/40 hover:border-white/20",
        )}
      >
        <span
          className={cn(
            "grid h-14 w-14 place-items-center rounded-2xl bg-gold-400/10 text-gold-300 transition-transform",
            dragOver && "scale-110",
          )}
        >
          <UploadCloud className="h-7 w-7" />
        </span>
        <p className="mt-4 text-base font-medium text-zinc-200">
          Drag & drop your photos here
        </p>
        <p className="mt-1 text-sm text-zinc-500">or</p>
        <Button
          variant="secondary"
          className="mt-3"
          onClick={() => inputRef.current?.click()}
        >
          <ImagePlus className="h-4 w-4" />
          Browse files
        </Button>
        <p className="mt-4 text-xs text-zinc-600">
          JPG, PNG, HEIC, WebP · your photos never leave your device in this demo
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          aria-label="Choose photos"
          onChange={(e) => {
            onFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {/* Thumbnail grid */}
      {photos.length > 0 ? (
        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm text-zinc-400">
              <span className="font-semibold text-zinc-200">{photos.length}</span>{" "}
              {photos.length === 1 ? "photo" : "photos"} · drag to reorder
            </p>
            <Button variant="ghost" size="sm" onClick={clearPhotos}>
              <Trash2 className="h-3.5 w-3.5" />
              Clear all
            </Button>
          </div>

          <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
            <AnimatePresence initial={false}>
              {photos.map((p, i) => (
                <motion.li
                  layout
                  key={p.id}
                  initial={{ opacity: 0, scale: 0.85 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.85 }}
                  transition={{ duration: 0.2 }}
                  draggable
                  onDragStart={() => setDraggingId(p.id)}
                  onDragEnd={() => setDraggingId(null)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    if (draggingId && draggingId !== p.id)
                      reorderPhotos(draggingId, p.id);
                    setDraggingId(null);
                  }}
                  className={cn(
                    "group relative aspect-square cursor-grab overflow-hidden rounded-xl border border-white/10 active:cursor-grabbing",
                    draggingId === p.id && "opacity-40",
                  )}
                >
                  <img
                    src={p.url}
                    alt={p.name}
                    className="h-full w-full object-cover"
                    draggable={false}
                  />
                  <span className="absolute left-1.5 top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-black/70 px-1 font-mono text-[10px] text-white/90">
                    {i + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => removePhoto(p.id)}
                    aria-label={`Remove ${p.name}`}
                    className="absolute right-1.5 top-1.5 grid h-6 w-6 place-items-center rounded-full bg-black/70 text-white/90 opacity-0 transition-opacity hover:bg-ember-500 focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      ) : (
        <p className="mt-8 text-center text-sm text-zinc-600">
          Your selected photos will appear here as a reorderable storyboard.
        </p>
      )}

      <div className="mt-10 flex items-center justify-between">
        <span className="text-xs text-zinc-600">
          Tip: 4–12 photos make the richest reel.
        </span>
        <Button
          size="lg"
          disabled={photos.length === 0}
          onClick={() => goTo("occasion")}
        >
          Choose an occasion
          <ArrowRight className="h-5 w-5" />
        </Button>
      </div>
    </div>
  );
}

export function StepHeading({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mb-8 text-center">
      <h2 className="font-display text-3xl font-semibold text-zinc-50 md:text-4xl">
        {title}
      </h2>
      <p className="mx-auto mt-3 max-w-xl text-balance text-zinc-400">{subtitle}</p>
    </div>
  );
}
