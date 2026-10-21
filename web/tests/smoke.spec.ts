import { expect, test, type Page } from "@playwright/test";

// The demo arc (docs/TESTING.md "Demo-day preparation"), one test per beat, against a real
// finished run. Defaults to the IoT demo run; override with ATLAS_SMOKE_RUN_ID.
const RUN = process.env.ATLAS_SMOKE_RUN_ID ?? "a0e32253-6a67-46e5-9b4e-6273c0aa1673";

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  return errors;
}

test("home is the search box; the sidebar lists runs and links to them", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/");
  await expect(page.getByLabel("Research question")).toBeVisible();
  await expect(page.getByLabel("Research question")).toBeFocused();
  await page.getByRole("button", { name: /open menu/i }).click();
  const sidebar = page.getByRole("dialog", { name: "Search history and settings" });
  await expect(sidebar).toBeInViewport();
  await expect(sidebar.locator(`a[href="/runs/${RUN}"]`)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sidebar).not.toBeInViewport();
  expect(errors).toEqual([]);
});

test("searches are remembered in the sidebar history and can be removed", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/");
  // seeded as Home.tsx's addSearch() records a new run, without starting a real crawl
  await page.evaluate(
    (runId) =>
      localStorage.setItem(
        "atlas-history",
        JSON.stringify([{ runId, query: "smoke-test search", mode: "standard", at: new Date().toISOString() }]),
      ),
    RUN,
  );
  await page.reload();
  await page.getByRole("button", { name: /open menu/i }).click();
  await page.getByRole("link", { name: /smoke-test search/ }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${RUN}$`));
  await page.getByRole("button", { name: /open menu/i }).click();
  await page.getByRole("button", { name: /remove “smoke-test search” from history/i }).click();
  await expect(page.getByText("No searches yet")).toBeVisible();
  expect(errors).toEqual([]);
});

test("run view draws the graph with its legend, stats and replayed log", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/runs/${RUN}`);
  await expect(page.locator('[aria-label="Citation and claim-relation graph"] canvas').first()).toBeVisible();
  await expect(page.getByText("ringed = read by ATLAS")).toBeVisible();
  await expect(page.getByTestId("run-stats")).toBeInViewport({ ratio: 1 }); // not clipped
  await expect(page.getByText("Read paper #1", { exact: false }).first()).toBeVisible(); // event log replayed
  expect(errors).toEqual([]);
});

test("report cites papers by number and lists them as references", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/runs/${RUN}/report`);
  await expect(page.getByRole("heading", { name: "References" })).toBeVisible();
  const firstCitation = page.locator("a", { hasText: /^\[1\]$/ }).first();
  await expect(firstCitation).toBeVisible();
  await expect(page.getByText(/\[doi:/)).toHaveCount(0); // no raw ids left in the prose
  await firstCitation.click();
  await expect(page).toHaveURL(new RegExp(`/runs/${RUN}/paper/`));
  expect(errors).toEqual([]);
});

test("clicking a claim highlights its verbatim quote inside the source text", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/runs/${RUN}/report`);
  await page.locator("a", { hasText: /^\[1\]$/ }).first().click();
  await expect(page.locator("mark").first()).toBeVisible({ timeout: 20_000 });
  const claim = page.locator("button[aria-pressed]").first();
  await claim.click();
  await expect(claim).toHaveAttribute("aria-pressed", "true");
  const selected = page.locator("mark.bg-yellow-300");
  await expect(selected).toBeVisible();
  // the highlighted span reads exactly like the claim's quote (the grounding gate, on screen)
  const quote = (await claim.locator("blockquote").innerText()).replace(/^“|”$/g, "");
  const squash = (s: string) => s.replace(/\s+/g, " ").trim();
  expect(squash(await selected.innerText())).toBe(squash(quote));
  expect(errors).toEqual([]);
});

test("chat refuses a question the corpus cannot answer", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto(`/runs/${RUN}/chat`);
  await page.getByRole("button", { name: "Test the refusal" }).click();
  await expect(page.getByText("ATLAS did not read anything that addresses this.")).toBeVisible({
    timeout: 30_000,
  });
  expect(errors).toEqual([]);
});

test("theme toggle switches to light and is remembered", async ({ page }) => {
  const errors = trackErrors(page);
  await page.goto("/");
  await page.evaluate(() => localStorage.setItem("atlas-theme", "dark"));
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: /open menu/i }).click(); // the toggle lives in the sidebar on home
  await page.getByRole("button", { name: /switch to light theme/i }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.goto(`/runs/${RUN}`); // survives navigation and a fresh load
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect(errors).toEqual([]);
});
