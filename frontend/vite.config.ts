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
    },
  };
});
