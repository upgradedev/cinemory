import { test, expect, type Page } from "@playwright/test";
import { mockCinemoryApi } from "./mocks";

// The four wizard steps, keyed by the animated wrapper's accessible name
// (aria-label = "Step N of 4: …") and the heading each step renders.
const STEPS = [
  { group: /step 1 of 4/i, heading: /bring your memories/i },
  { group: /step 2 of 4/i, heading: /set the mood/i },
  { group: /step 3 of 4/i, heading: /rolling/i },
  { group: /step 4 of 4/i, heading: /your reel is ready/i },
] as const;

/**
 * The load-bearing assertion. The animated wrapper (role="group") must settle
 * at opacity:1. jsdom resolves framer-motion synchronously so the vitest suite
 * never sees this; a real browser hitting the AnimatePresence mode="wait"
 * dead-end leaves the incoming wrapper stuck at its initial opacity:0 (or never
 * mounts it at all) — either way this times out. NOTE: opacity is NOT inherited
 * and Playwright's toBeVisible() ignores opacity, so we must read opacity on the
 * wrapper itself, not on a child heading.
 */
async function assertStepSettled(
  page: Page,
  step: { group: RegExp; heading: RegExp },
): Promise<void> {
  const wrapper = page.getByRole("group", { name: step.group });
  await expect(wrapper, `step "${step.group}" wrapper never settled to opacity:1`).toHaveCSS(
    "opacity",
    "1",
  );
  await expect(wrapper).toBeVisible();
  await expect(page.getByRole("heading", { name: step.heading })).toBeVisible();
}

async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  // 1px tolerance for sub-pixel rounding; anything larger is a real overflow.
  expect(
    scrollWidth,
    `horizontal overflow at ${label}: scrollWidth ${scrollWidth} > innerWidth ${innerWidth}`,
  ).toBeLessThanOrEqual(innerWidth + 1);
}

/** Visible, enabled buttons/links whose rendered box is under 44×44 (WCAG 2.5.5
 *  AAA tap-target). sr-only helpers (skip link) and aria-hidden nodes exempt. */
async function tapTargetViolations(page: Page) {
  return page.evaluate(() => {
    const MIN = 44;
    const out: Array<{ label: string; w: number; h: number }> = [];
    const controls = document.querySelectorAll<HTMLElement>("a[href], button:not([disabled])");
    for (const el of Array.from(controls)) {
      if (el.closest(".sr-only") || el.closest('[aria-hidden="true"]')) continue;
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue; // not laid out
      if (r.width < MIN - 0.5 || r.height < MIN - 0.5) {
        out.push({
          label: (el.textContent || "").trim().slice(0, 32) || el.getAttribute("aria-label") || el.tagName,
          w: Math.round(r.width),
          h: Math.round(r.height),
        });
      }
    }
    return out;
  });
}

interface WalkOpts {
  label: string;
  checkTapTargets?: boolean;
}

/** Drive the full landing → upload → occasion → generate → result → verify
 *  journey, asserting each step's animated panel actually mounts and reaches
 *  opacity:1, plus no horizontal overflow (and, on mobile, tap-target sizes). */
async function walkJourney(page: Page, opts: WalkOpts): Promise<void> {
  await mockCinemoryApi(page);
  await page.goto("/");

  // Landing renders and the primary CTA is reachable.
  await expect(page.getByRole("heading", { level: 1, name: /made into film/i })).toBeVisible();
  await assertNoHorizontalOverflow(page, `${opts.label} landing`);
  if (opts.checkTapTargets) {
    expect(await tapTargetViolations(page), `tap targets on landing`).toEqual([]);
  }
  await page.getByRole("button", { name: /create your reel/i }).click();

  // Step 1 — Photos.
  await assertStepSettled(page, STEPS[0]);
  await assertNoHorizontalOverflow(page, `${opts.label} upload`);
  await page.getByRole("button", { name: /try with sample photos/i }).click();
  // Sample photos are painted on a canvas; wait until the CTA unlocks.
  const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
  await expect(toOccasion).toBeEnabled();
  if (opts.checkTapTargets) {
    expect(await tapTargetViolations(page), `tap targets on upload (with photos)`).toEqual([]);
  }
  await toOccasion.click();

  // Step 2 — Occasion. THE regression point: with mode="wait" this panel
  // dead-ends at opacity:0 and the wizard blanks here.
  await assertStepSettled(page, STEPS[1]);
  await assertNoHorizontalOverflow(page, `${opts.label} occasion`);
  await page.getByRole("radio", { name: /wedding/i }).click();
  await page.getByRole("button", { name: /generate my reel/i }).click();

  // Step 3 — Generate (transient; the mock adds a short delay so it is stably
  // observable before the auto-advance to the result).
  await assertStepSettled(page, STEPS[2]);
  await assertNoHorizontalOverflow(page, `${opts.label} generate`);

  // Step 4 — Result.
  await assertStepSettled(page, STEPS[3]);
  await assertNoHorizontalOverflow(page, `${opts.label} result`);
  if (opts.checkTapTargets) {
    expect(await tapTargetViolations(page), `tap targets on result`).toEqual([]);
  }

  // The provenance panel is reachable and its in-browser Verify works.
  await expect(page.getByRole("heading", { name: /^provenance$/i })).toBeVisible();
  const verifyBtn = page.getByRole("button", { name: /verify provenance/i });
  await expect(verifyBtn).toBeVisible();
  await verifyBtn.click();
  await expect(page.getByText(/it matches the sealed manifest_hash/i)).toBeVisible();
  await expect(page.getByText(/verified/i).first()).toBeVisible();

  // The server-side aggregate re-verification receipt also renders: a text
  // summary (never colour alone) plus the individual named checks.
  await expect(page.getByText(/checks passed — all verified/i)).toBeVisible();
  await expect(page.getByText(/reel bytes match the sealed hash/i)).toBeVisible();
  await assertNoHorizontalOverflow(page, `${opts.label} result (verified)`);
}

for (const width of [375, 768, 1280] as const) {
  test(`wizard journey mounts every step with no dead-end @${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 500 ? 812 : 900 });
    await walkJourney(page, { label: `${width}px`, checkTapTargets: width === 375 });
  });
}

// The landing's secondary CTA is its own entry path (per the demo-mode e2e
// rule): it must generate the sample set and drop the visitor into the studio
// already holding the storyboard, then reach a sealed, verifiable reel.
test("landing 'Try with sample photos' loads the storyboard and reaches a sealed reel", async ({
  page,
}) => {
  await mockCinemoryApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: /made into film/i }),
  ).toBeVisible();

  await page.getByRole("button", { name: /try with sample photos/i }).click();

  // Lands on step 1 with the sample storyboard already populated (descriptive
  // alt, not a filename) and the next CTA unlocked.
  await assertStepSettled(page, STEPS[0]);
  await expect(page.getByAltText(/cinematic dawn/i)).toBeVisible();
  const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
  await expect(toOccasion).toBeEnabled();
  await toOccasion.click();

  await assertStepSettled(page, STEPS[1]);
  await page.getByRole("radio", { name: /wedding/i }).click();
  await page.getByRole("button", { name: /generate my reel/i }).click();
  await assertStepSettled(page, STEPS[2]);
  await assertStepSettled(page, STEPS[3]);

  await page.getByRole("button", { name: /verify provenance/i }).click();
  await expect(page.getByText(/it matches the sealed manifest_hash/i)).toBeVisible();
});
