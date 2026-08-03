import { test, expect, type Page } from "@playwright/test";
import { mockCinemoryApi } from "./mocks";

/**
 * Guard: the consumer path must not leak developer vocabulary.
 *
 * Mirrors the sibling ClaimScene repo's `e2e/plain-language.spec.ts`: same
 * idea (walk the real journey, fail on the vocabulary itself, in CI instead
 * of waiting for a human to notice), adapted to Cinemory's own journey and
 * vocabulary. Cinemory never says "VLM"; its own leak-prone seams are the
 * health/ops surface and the specific models and cloud that sit behind
 * Genblaze. Writing this guard found one real, live leak (see the second
 * test below), fixed in the same change as the guard itself.
 *
 * Scope, stated honestly:
 *  - It checks what is VISIBLE (innerText), so it cannot see a tooltip that
 *    only appears on hover (e.g. the offline badge's `title` attribute).
 *  - The Provenance panel (`ProvenancePanel.tsx`, reachable on the result
 *    step, and its equivalent inside "My reels") is deliberately EXEMPT.
 *    That panel is Cinemory's own forensic audit trail: it renders the real
 *    provider and model of every generative step straight from the sealed
 *    manifest (today: "fake-genblaze" / "Kling-Image2Video-V2.1-Master" in
 *    the golden fixture), which is exactly the kind of raw technical fact
 *    that must be reproduced verbatim there, not prettified. Technical
 *    wording is correct there. It is not correct on the way in.
 *  - It is a vocabulary check, not a readability score. Copy can still be
 *    bad English while passing.
 */

/** Words that mean something to us and nothing to someone cutting a wedding
 *  or anniversary reel. */
const JARGON = [
  /\bAPI\b/i,
  /\bbackend\b/i,
  /\bendpoint\b/i,
  /\blocalhost\b/i,
  /\bB2Storage\b/i, // the storage adapter's class name; "Backblaze B2" (the brand credit) is fine
  /\bGMI\b/i, // the cloud Genblaze's live models run on, never named to a visitor
  /\bKling\b/i, // the underlying image-to-video model codename
  /\bseedance\b/i, // the underlying chapter-bridge model codename
  /\bpipeline\b/i,
];

/** Symptoms of a rendering bug that should never reach a screen either. */
const BROKEN_RENDER = [/\[object Object\]/, /\bundefined\b/, /\bNaN\b/];

async function assertPlainLanguage(page: Page, where: string, text?: string) {
  const body = text ?? (await page.locator("body").innerText());
  for (const pattern of [...JARGON, ...BROKEN_RENDER]) {
    expect(body, `${where}: leaked "${pattern.source}" into the visible UI`).not.toMatch(pattern);
  }
}

const PROVENANCE_SELECTOR = '[aria-labelledby="provenance-heading"]';

/**
 * Real rendered `document.body.innerText`, with the given subtree(s)
 * temporarily hidden (`display:none`, then restored) rather than absent from
 * the DOM. This stays true "visible text" semantics, unlike subtracting one
 * innerText string from another, which silently no-ops if the excluded
 * subtree's own innerText does not match byte-for-byte how it renders inside
 * the full page (whitespace collapsing differs by context).
 */
async function bodyTextExcluding(page: Page, selector: string): Promise<string> {
  return page.evaluate((sel) => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(sel));
    const prevDisplay = nodes.map((n) => n.style.display);
    nodes.forEach((n) => {
      n.style.display = "none";
    });
    const text = document.body.innerText;
    nodes.forEach((n, i) => {
      n.style.display = prevDisplay[i];
    });
    return text;
  }, selector);
}

test("the consumer path never shows developer vocabulary", async ({ page }) => {
  await mockCinemoryApi(page);
  await page.goto("/");
  await assertPlainLanguage(page, "landing");

  await page.getByRole("button", { name: /create your reel/i }).click();
  await expect(page.getByRole("heading", { name: /bring your memories/i })).toBeVisible();
  await assertPlainLanguage(page, "step 1 (photos, on arrival)");

  // Scan again AFTER loading sample photos, not just on arrival: the same
  // lesson ClaimScene's version of this spec learned the hard way. The first
  // version of that spec checked its step 1 only on arrival and missed a
  // line that appeared once a sample was selected. Copy conditional on state
  // needs a scan in that state.
  await page.getByRole("button", { name: /try with sample photos/i }).click();
  const toOccasion = page.getByRole("button", { name: /choose an occasion/i });
  await expect(toOccasion).toBeEnabled();
  await assertPlainLanguage(page, "step 1 (photos, sample photos loaded)");
  await toOccasion.click();

  await expect(page.getByRole("heading", { name: /set the mood/i })).toBeVisible();
  await assertPlainLanguage(page, "step 2 (occasion, on arrival)");

  // Same lesson again: scan after picking an occasion, a second state change
  // on the same step (the "pick an occasion to continue" hint disappears).
  await page.getByRole("radio", { name: /wedding/i }).click();
  await assertPlainLanguage(page, "step 2 (occasion, wedding selected)");
  await page.getByRole("button", { name: /generate my reel/i }).click();

  await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
  await assertPlainLanguage(page, "step 3 (generating)");

  await expect(page.getByRole("heading", { name: /your reel is ready/i })).toBeVisible();
  // Sanity check that the exemption below actually has something to exempt:
  // if this ever fails, ProvenancePanel's markup changed and the selector
  // needs updating, not the jargon list.
  await expect(page.getByRole("region", { name: /^provenance$/i })).toBeVisible();

  const fullText = await page.locator("body").innerText();
  const withoutProvenance = await bodyTextExcluding(page, PROVENANCE_SELECTOR);
  expect(
    withoutProvenance.length,
    "excluding the Provenance panel removed nothing; PROVENANCE_SELECTOR is probably stale",
  ).toBeLessThan(fullText.length);
  await assertPlainLanguage(page, "step 4 (result, excluding Provenance panel)", withoutProvenance);
});

test("the generation stage list explains itself without naming a model or cloud", async ({ page }) => {
  // The wording people see while waiting is the most-read copy in the app.
  // This pins the exact regression pattern this guard exists to catch, the
  // same way ClaimScene's sibling test pins its own extraction-ladder line.
  await mockCinemoryApi(page);
  await page.goto("/");
  await page.getByRole("button", { name: /create your reel/i }).click();
  await page.getByRole("button", { name: /try with sample photos/i }).click();
  await expect(page.getByRole("button", { name: /choose an occasion/i })).toBeEnabled();
  await page.getByRole("button", { name: /choose an occasion/i }).click();
  await page.getByRole("radio", { name: /wedding/i }).click();
  await page.getByRole("button", { name: /generate my reel/i }).click();

  await expect(page.getByRole("heading", { name: /rolling/i })).toBeVisible();
  await expect(page.getByText(/Kling/i)).toHaveCount(0);
  await expect(page.getByText(/GMI/i)).toHaveCount(0);
  await expect(page.getByText(/seedance/i)).toHaveCount(0);
});

test("the offline health badge explains itself without naming the API", async ({ page }) => {
  // Copy conditional on state needs a scan in that state: the exact bug
  // class this guard exists to catch. Every other spec (this file's first
  // test included) always mocks a healthy /health, so the badge that only
  // renders when the health check ERRORS is invisible to them. Registered
  // AFTER mockCinemoryApi, so it wins: Playwright tries routes in reverse
  // registration order, and this one fulfills/aborts directly, so the
  // earlier healthy-/health handler never runs.
  await mockCinemoryApi(page);
  await page.route("**/health", (route) => route.abort("failed"));

  await page.goto("/");
  await expect(page.getByText(/offline/i)).toBeVisible();
  await assertPlainLanguage(page, "landing (health check failed)");
});
