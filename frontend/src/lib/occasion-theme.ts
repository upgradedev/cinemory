// Evocative visual identity for each occasion preset. Keyed by the backend
// occasion `key`; falls back to a neutral cinematic gradient for unknown keys
// so new server-side presets still render gracefully.

export interface OccasionTheme {
  gradient: string; // tailwind gradient classes for the card surface
  glow: string; // accent color for hover glow
  emoji: string;
  tagline: string;
}

const THEMES: Record<string, OccasionTheme> = {
  anniversary: {
    gradient: "from-rose-500/25 via-amber-500/10 to-transparent",
    glow: "rgba(244,114,182,0.35)",
    emoji: "💞",
    tagline: "Warm, intimate, timeless",
  },
  graduation: {
    gradient: "from-amber-400/25 via-yellow-500/10 to-transparent",
    glow: "rgba(216,178,90,0.4)",
    emoji: "🎓",
    tagline: "Triumphant golden-hour glow",
  },
  birthday: {
    gradient: "from-fuchsia-500/25 via-orange-400/10 to-transparent",
    glow: "rgba(232,121,249,0.35)",
    emoji: "🎂",
    tagline: "Bright, festive, joyful",
  },
  wedding: {
    gradient: "from-sky-300/20 via-rose-200/10 to-transparent",
    glow: "rgba(186,230,253,0.35)",
    emoji: "💍",
    tagline: "Dreamy bokeh, forever",
  },
  "year-in-review": {
    gradient: "from-violet-500/25 via-cyan-400/10 to-transparent",
    glow: "rgba(139,92,246,0.35)",
    emoji: "🗓️",
    tagline: "Fast, vibrant, highlight-reel",
  },
  "business-event": {
    gradient: "from-slate-400/20 via-gold-400/10 to-transparent",
    glow: "rgba(148,163,184,0.35)",
    emoji: "🏆",
    tagline: "Polished, premium, credible",
  },
};

const FALLBACK: OccasionTheme = {
  gradient: "from-gold-400/20 via-ember-400/5 to-transparent",
  glow: "rgba(216,178,90,0.35)",
  emoji: "🎬",
  tagline: "A cinematic memory",
};

export function occasionTheme(key: string): OccasionTheme {
  return THEMES[key] ?? FALLBACK;
}
