import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockCinemoryApi } from "./mocks";

// The gate: zero axe violations at impact "serious" or "critical" on the landing
// and every wizard step. (target-size and visible-focus are not auto-testable by
// axe — those live in journey.spec.ts and the focus-ring test below.)
const BLOCKING = new Set(["serious", "critical"]);

async function seriousViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  return violations
    .filter((v) => BLOCKING.has(v.impact ?? ""))
    .map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target, html: n.html.slice(0, 120) })),
    }));
}

type Stop = "landing" | "upload" | "upload-photos" | "occasion" | "generate" | "result";

/** Advance the app to a given point so axe can scan that exact screen. */
async function reach(page: Page, stop: Stop): Promise<void> {
  await mockCinemoryApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: /made into film/i })).toBeVisible();
  if (stop === "landing") return;

  await page.getByRole("button", { name: /create your reel/i }).click();
  await expect(page.getByRole("heading", { name: /bring your memories/i })).toBeVisible();
  if (stop === "upload") return;

  await page.getByRole("button", { name: /try with sample photos/i }).click();
  await expect(page.getByRole("button", { name: /choose an occasion/i })).toBeEnabled();
  if (stop === "upload-photos") return;

  await page.getByRole("button", { name: /choose an occasion/i }).click();
  await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();
  if (stop === "occasion") return;

  await page.getByRole("radio", { name: /wedding/i }).click();
  await page.getByRole("button", { name: /generate my reel/i }).click();
  await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
  if (stop === "generate") return;

  await expect(page.getByRole("heading", { name: /your reel is ready/i })).toBeVisible();
}

const STOPS: Stop[] = ["landing", "upload", "upload-photos", "occasion", "generate", "result"];

for (const stop of STOPS) {
  test(`no serious/critical axe violations — ${stop}`, async ({ page }) => {
    await reach(page, stop);
    const violations = await seriousViolations(page);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });
}

test("primary CTA shows a visible focus ring under keyboard navigation", async ({ page }) => {
  await mockCinemoryApi(page);
  await page.goto("/");
  const cta = page.getByRole("button", { name: /create your reel/i });
  await cta.scrollIntoViewIfNeeded();

  // Tab (keyboard modality → :focus-visible) until the CTA is focused.
  let focused = false;
  for (let i = 0; i < 25 && !focused; i += 1) {
    await page.keyboard.press("Tab");
    focused = await cta.evaluate((el) => el === document.activeElement);
  }
  expect(focused, "could not reach the primary CTA via keyboard").toBe(true);

  const ring = await cta.evaluate((el) => {
    const s = getComputedStyle(el);
    return {
      focusVisible: el.matches(":focus-visible"),
      boxShadow: s.boxShadow,
      outlineStyle: s.outlineStyle,
      outlineWidth: s.outlineWidth,
    };
  });
  expect(ring.focusVisible, "CTA is not matched by :focus-visible on keyboard focus").toBe(true);
  const hasRing =
    (ring.boxShadow !== "none" && ring.boxShadow !== "") ||
    (ring.outlineStyle !== "none" && ring.outlineWidth !== "0px");
  expect(hasRing, `no visible focus ring computed: ${JSON.stringify(ring)}`).toBe(true);
});
