import { defineConfig, devices } from "@playwright/test";

// Real-browser end-to-end gate for the Cinemory wizard.
//
// Why this exists: the vitest suite runs in jsdom, which resolves framer-motion
// synchronously — so a transition that dead-ends in a real browser (the
// AnimatePresence mode="wait" bug) passed every jsdom test yet blanked the
// wizard for judges. These specs drive the *built* app in headless Chromium and
// assert the animated wrapper actually reaches opacity:1 at every step, plus
// responsive/tap-target/axe gates the component tests structurally cannot see.
//
// The API is mocked at the network boundary (see e2e/mocks.ts, page.route), so
// the journey is deterministic and needs no backend, no credentials, no CORS.
const PORT = 4173;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "on-first-retry",
    // Deterministic viewport; individual specs resize to 375/768/1280.
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  // Build the production bundle and serve it exactly as Firebase Hosting would
  // (vite preview). Self-contained: `npx playwright test` works from a clean
  // checkout with no prior build. In CI we never reuse a stale server.
  webServer: {
    // Bind explicitly to IPv4 so `localhost` (which resolves to 127.0.0.1 on
    // most hosts) always reaches it — vite preview's default can bind IPv6-only.
    command: `npm run build && npx vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
