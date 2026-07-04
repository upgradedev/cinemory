/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: { "2xl": "1200px" },
    },
    extend: {
      colors: {
        // Cinematic dark palette: near-black film stock + warm gold key light.
        ink: {
          950: "#08080a",
          900: "#0b0b0f",
          800: "#111117",
          700: "#181820",
          600: "#22222c",
          500: "#33333f",
        },
        gold: {
          50: "#fbf6ec",
          200: "#ecd6a8",
          300: "#e2c47f",
          400: "#d8b25a",
          500: "#c8983a",
          600: "#a8792a",
        },
        ember: {
          400: "#f0714f",
          500: "#e2543a",
        },
        border: "hsl(240 6% 20% / 0.6)",
        ring: "#d8b25a",
      },
      fontFamily: {
        display: ['"Fraunces"', "ui-serif", "Georgia", "serif"],
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 60px -12px rgba(216,178,90,0.35)",
        "glow-sm": "0 0 24px -8px rgba(216,178,90,0.4)",
        film: "0 20px 60px -20px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.04)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "film-sheen":
          "linear-gradient(120deg, transparent 20%, rgba(255,255,255,0.06) 50%, transparent 80%)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        "reel-spin": {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.22,1,0.36,1) both",
        shimmer: "shimmer 2s infinite",
        "pulse-glow": "pulse-glow 3s ease-in-out infinite",
        "reel-spin": "reel-spin 3s linear infinite",
      },
    },
  },
  plugins: [],
};
