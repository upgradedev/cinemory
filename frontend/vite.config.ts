/// <reference types="vitest" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// The single-origin contract: in production the frontend is served by Firebase
// Hosting, which rewrites the real API routes to the Cloud Run `cinemory`
// service (see firebase.json) — so the browser always talks same-origin and
// there is never any CORS. In dev we reproduce that same-origin illusion with
// Vite's proxy: the browser calls http://localhost:5173/occasions and Vite
// forwards it to VITE_API_BASE (the Cloud Run URL, or a local backend). This
// means the app code uses relative paths everywhere and needs zero CORS.
const API_ROUTES = ["/health", "/occasions", "/reels"];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget =
    env.VITE_DEV_PROXY_TARGET ||
    env.VITE_API_BASE ||
    "https://cinemory-595784992266.europe-west1.run.app";

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      port: 5173,
      proxy: Object.fromEntries(
        API_ROUTES.map((route) => [
          route,
          { target: proxyTarget, changeOrigin: true, secure: true },
        ]),
      ),
    },
    build: {
      outDir: "dist",
      sourcemap: false,
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: true,
      coverage: {
        provider: "v8",
        // Count EVERY source file, not only the ones a test imports — so the
        // percentage is honest and an untested component shows as 0%, never
        // silently excluded from the denominator.
        all: true,
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/main.tsx", // React root bootstrap (createRoot glue) — no logic
          "src/test/**", // test setup + fixtures
          "src/**/*.test.{ts,tsx}",
          "src/**/*.d.ts",
        ],
        reporter: ["text-summary", "text", "html"],
        // Calibrated to what the suite actually achieves (measured: lines +
        // statements 98.5%, functions 100%, branches 90%). Lines/statements/
        // functions gate at 90 (firm floors with headroom); branches at 85 (an
        // honest floor below the measured 90% — React has many tiny inline JSX
        // handler branches). Never set a threshold above measured.
        thresholds: { lines: 90, statements: 90, branches: 85, functions: 90 },
      },
    },
  };
});
