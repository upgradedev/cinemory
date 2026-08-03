import { test, expect, type Locator, type Page } from "@playwright/test";
import { mockCinemoryApi } from "./mocks";

/**
 * Responsive layout gate for the Cinemory wizard.
 *
 *  - No horizontal overflow at 375 / 768 / 1280 through the full wizard
 *    (landing, upload, occasion, generate, result).
 *  - Primary CTAs are >=44x44px tap targets on mobile (WCAG 2.5.5).
 *  - The occasion cards collapse to a single column below the sm breakpoint
 *    (OccasionPicker's `grid sm:grid-cols-2 lg:grid-cols-3`), and the result
 *    step's player/provenance layout collapses to a single column below the
 *    lg breakpoint (ReelResult's `grid lg:grid-cols-5` with a 3/2 span
 *    split) - both go multi-column again at tablet/desktop.
 */

const WIDTHS = [375, 768, 1280] as const;

async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  // 1px tolerance for sub-pixel rounding, matching journey.spec.ts's own check.
  expect(
    scrollWidth,
    `horizontal overflow at ${label}: scrollWidth ${scrollWidth} > innerWidth ${innerWidth}`,
  ).toBeLessThanOrEqual(innerWidth + 1);
}

test.beforeEach(async ({ page }) => {
  await mockCinemoryApi(page);
});

for (const width of WIDTHS) {
  test(`no horizontal overflow at ${width}px (landing to result)`, async ({ page }) => {
    await page.setViewportSize({ width, height: width < 500 ? 812 : 900 });

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /made into film/i })).toBeVisible();
    await assertNoHorizontalOverflow(page, `landing@${width}`);

    await page.getByRole("button", { name: /create your reel/i }).click();
    await expect(page.getByRole("heading", { name: /bring your memories/i })).toBeVisible();
    await assertNoHorizontalOverflow(page, `upload@${width}`);

    await page.getByRole("button", { name: /try with sample photos/i }).click();
    const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
    await expect(toOccasion).toBeEnabled();
    await toOccasion.click();

    await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();
    await assertNoHorizontalOverflow(page, `occasion@${width}`);

    await page.getByRole("radio", { name: /wedding/i }).click();
    await page.getByRole("button", { name: /generate my reel/i }).click();

    await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
    await assertNoHorizontalOverflow(page, `generate@${width}`);

    await expect(page.getByRole("heading", { name: /your reel is ready/i })).toBeVisible();
    await assertNoHorizontalOverflow(page, `result@${width}`);
  });
}

test("primary CTAs meet the 44px tap-target minimum on mobile (375px)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });

  const atLeast44 = async (loc: Locator, name: string) => {
    await expect(loc, `${name} present`).toBeVisible();
    const box = await loc.boundingBox();
    expect(box, `${name} has a layout box`).not.toBeNull();
    expect(box!.width, `${name} width >=44 (got ${box!.width})`).toBeGreaterThanOrEqual(44);
    expect(box!.height, `${name} height >=44 (got ${box!.height})`).toBeGreaterThanOrEqual(44);
  };

  await page.goto("/");
  await atLeast44(page.getByRole("button", { name: /create your reel/i }), "Create your reel CTA");
  await atLeast44(
    page.getByRole("button", { name: /try with sample photos/i }),
    "Try with sample photos CTA (landing)",
  );

  await page.getByRole("button", { name: /create your reel/i }).click();
  await expect(page.getByRole("heading", { name: /bring your memories/i })).toBeVisible();
  await page.getByRole("button", { name: /try with sample photos/i }).click();
  const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
  await expect(toOccasion).toBeEnabled();
  await atLeast44(toOccasion, "Choose an occasion CTA");

  await toOccasion.click();
  await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();
  await page.getByRole("radio", { name: /wedding/i }).click();
  await atLeast44(
    page.getByRole("button", { name: /generate my reel/i }),
    "Generate my reel CTA",
  );
});

test("occasion cards go from a single column on mobile to multiple columns on tablet/desktop", async ({
  page,
}) => {
  for (const { width, expectedColumns } of [
    { width: 375, expectedColumns: 1 },
    { width: 768, expectedColumns: 2 },
    { width: 1280, expectedColumns: 3 },
  ] as const) {
    await page.setViewportSize({ width, height: 900 });

    await page.goto("/");
    await page.getByRole("button", { name: /create your reel/i }).click();
    await page.getByRole("button", { name: /try with sample photos/i }).click();
    const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
    await expect(toOccasion).toBeEnabled();
    await toOccasion.click();
    await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();

    // Scope to the picker's own radiogroup, and POLL the count: the cards
    // mount with an entrance animation, so a single count() can land while
    // only some of them are attached. Polling waits for the real number
    // instead of weakening the assertion.
    const cards = page.getByRole("radiogroup").getByRole("radio");
    await expect(cards.first()).toBeVisible();
    await expect
      .poll(() => cards.count(), { message: `occasion cards render at ${width}px` })
      .toBeGreaterThan(3);
    const count = await cards.count();

    // The cards slide in on a stagger, so measuring on first paint catches
    // them mid-flight: a single column reads as several left edges a few px
    // apart and the count comes out too high. Widening the cluster tolerance
    // would hide that rather than fix it, and would also stop the test from
    // noticing a genuinely wrong layout. Wait for the geometry to stop moving
    // instead, then measure once.
    const readLefts = async (): Promise<number[]> => {
      const xs: number[] = [];
      for (let i = 0; i < count; i++) {
        const box = await cards.nth(i).boundingBox();
        expect(box, `card ${i} has a layout box at ${width}px`).not.toBeNull();
        xs.push(box!.x);
      }
      return xs;
    };
    let lefts = await readLefts();
    for (let settle = 0; settle < 20; settle++) {
      const again = await readLefts();
      if (again.every((x, i) => Math.abs(x - lefts[i]) < 0.5)) break;
      lefts = again;
      await page.waitForTimeout(100);
    }
    // Cluster left edges with a small tolerance (sub-pixel noise, not a real
    // extra column) to count how many distinct columns actually rendered.
    const columns: number[] = [];
    for (const x of lefts) {
      if (!columns.some((c) => Math.abs(c - x) < 8)) columns.push(x);
    }
    expect(
      columns.length,
      `expected ${expectedColumns} column(s) at ${width}px, left edges: ${lefts.join(", ")}`,
    ).toBe(expectedColumns);
  }
});

test("result step: player and provenance panel stack in a single column below desktop width", async ({
  page,
}) => {
  for (const { width, singleColumn } of [
    { width: 375, singleColumn: true },
    { width: 768, singleColumn: true },
    { width: 1280, singleColumn: false },
  ] as const) {
    await page.setViewportSize({ width, height: 900 });

    await page.goto("/");
    await page.getByRole("button", { name: /create your reel/i }).click();
    await page.getByRole("button", { name: /try with sample photos/i }).click();
    const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
    await expect(toOccasion).toBeEnabled();
    await toOccasion.click();
    await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();
    await page.getByRole("radio", { name: /wedding/i }).click();
    await page.getByRole("button", { name: /generate my reel/i }).click();
    await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /your reel is ready/i })).toBeVisible();

    // Two proven anchors (both already load-bearing in journey.spec.ts): the
    // step wrapper's left edge is the row's own left edge, and the
    // Provenance heading sits at a small, constant offset inside its own
    // grid column. Single column: that column IS the row, so the offset
    // between them stays small. Two columns (>=lg): the provenance column
    // starts well to the right of the player column, so the offset jumps by
    // several hundred pixels. This needs no assumption about the
    // container's own max-width resolution at each breakpoint.
    const stepWrapper = page.getByRole("group", { name: /step 4 of 4/i });
    const provenanceHeading = page.getByRole("heading", { name: /^provenance$/i });
    await expect(provenanceHeading).toBeVisible();

    const wrapperBox = await stepWrapper.boundingBox();
    const headingBox = await provenanceHeading.boundingBox();
    expect(wrapperBox, `step wrapper has a layout box at ${width}px`).not.toBeNull();
    expect(headingBox, `provenance heading has a layout box at ${width}px`).not.toBeNull();
    const offset = headingBox!.x - wrapperBox!.x;

    if (singleColumn) {
      expect(
        offset,
        `expected the provenance panel flush with the player column at ${width}px (offset ${offset})`,
      ).toBeLessThan(150);
    } else {
      expect(
        offset,
        `expected the provenance panel offset into a second column at ${width}px (offset ${offset})`,
      ).toBeGreaterThan(300);
    }
  }
});
