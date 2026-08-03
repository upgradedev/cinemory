import { test, expect } from "@playwright/test";
import { E2E_JOB_ID, mockCinemoryApi } from "./mocks";

/**
 * Losing the tab must not lose the reel.
 *
 * A reel takes minutes. Before this, a refresh, an accidental close or a
 * browser reload threw the whole in-flight run away even though the work
 * carried on server-side. These specs drive the real thing in a real browser:
 * the address bar gains the reel while it is still being made, a genuine
 * `page.reload()` picks it back up, and a link that leads nowhere says so
 * rather than spinning.
 *
 * jsdom cannot check any of this honestly — it has no address bar to reload
 * and no layout to measure the 44px tap target with.
 */

const NOT_FOUND = /couldn’t find that reel|couldn't find that reel/i;

async function startAReel(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /create your reel/i }).click();
  await page.getByRole("button", { name: /try with sample photos/i }).click();
  const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
  await expect(toOccasion).toBeEnabled();
  await toOccasion.click();
  await page.getByRole("radio", { name: /wedding/i }).click();
  await page.getByRole("button", { name: /generate my reel/i }).click();
}

test("the reel goes into the address bar while it is still being made", async ({ page }) => {
  await mockCinemoryApi(page);
  await startAReel(page);

  await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
  // Not when it finishes: while it is running, which is exactly when someone
  // refreshes and used to lose everything.
  await expect(page).toHaveURL(new RegExp(`#reel/${E2E_JOB_ID}$`));
  // And the visitor is told the link is safe to leave.
  await expect(page.getByText(/come back to this link later/i)).toBeVisible();
});

test("a real page reload picks the reel back up instead of starting blank", async ({ page }) => {
  await mockCinemoryApi(page);
  await startAReel(page);
  await expect(page).toHaveURL(new RegExp(`#reel/${E2E_JOB_ID}$`));

  await page.reload();

  // Straight back into the reel, never the landing page or step 1.
  await expect(page.getByRole("heading", { name: /your reel is ready/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /create your reel/i })).toHaveCount(0);
});

test("a mistyped link says so at once, with no request and no spinner", async ({ page }) => {
  await mockCinemoryApi(page);
  const polls: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/reels/jobs/")) polls.push(r.url());
  });

  await page.goto("/#reel/not-a-real-id!!");

  await expect(page.getByRole("heading", { name: NOT_FOUND })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  expect(polls, "asked the server about an id that cannot exist").toEqual([]);
});

test("an unknown reel answers the same way, in seconds", async ({ page }) => {
  await mockCinemoryApi(page);
  // Registered after the shared mocks so it wins: an id that looks real but
  // has no reel behind it, which is how an expired link answers.
  await page.route(
    (url) => url.pathname.startsWith("/reels/jobs/"),
    (route) => route.fulfill({ status: 404, json: { detail: "no job" } }),
  );

  await page.goto("/#reel/goneforever123");

  // A 404 is a final answer, not a blip to retry, so this lands well inside
  // the poll interval budget it used to burn first.
  await expect(page.getByRole("heading", { name: NOT_FOUND })).toBeVisible({
    timeout: 5000,
  });
});

test("the fresh start from a dead link clears the link and works at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockCinemoryApi(page);
  await page.goto("/#reel/nope!");

  const startNew = page.getByRole("button", { name: /start a new reel/i });
  await expect(startNew).toBeVisible();
  const box = await startNew.boundingBox();
  expect(box!.height, `tap target height (got ${box!.height})`).toBeGreaterThanOrEqual(44);
  expect(box!.width, `tap target width (got ${box!.width})`).toBeGreaterThanOrEqual(44);

  // The page must not scroll sideways on the narrowest phone.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "horizontal overflow at 375px").toBeLessThanOrEqual(1);

  await startNew.click();
  await expect(page.getByRole("heading", { name: /bring your memories/i })).toBeVisible();
  // A refresh after starting over must not reopen the dead link.
  await expect(page).not.toHaveURL(/#reel\//);
});
