// Screenshot every dashboard route at projector and laptop sizes, and record any page or
// console errors. Needs a running server: `atlas serve` (or `npm run dev`).
//   node scripts/screenshots.mjs <run_id> [base_url] [out_dir] [dark|light]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const runId = process.argv[2];
const base = process.argv[3] ?? "http://127.0.0.1:8000";
const out = process.argv[4] ?? "screenshots";
const theme = process.argv[5] ?? "dark"; // dark | light
if (!runId) throw new Error("usage: node scripts/screenshots.mjs <run_id> [base_url] [out_dir]");
mkdirSync(out, { recursive: true });

const sizes = { projector: { width: 1920, height: 1080 }, laptop: { width: 1366, height: 768 } };
const routes = {
  home: "/",
  run: `/runs/${runId}`,
  report: `/runs/${runId}/report`,
  chat: `/runs/${runId}/chat`,
};

const browser = await chromium.launch();
const problems = [];
for (const [sizeName, viewport] of Object.entries(sizes)) {
  const page = await browser.newPage({ viewport });
  await page.addInitScript((t) => localStorage.setItem("atlas-theme", t), theme);
  page.on("pageerror", (e) => problems.push(`${sizeName} pageerror: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && problems.push(`${sizeName} console: ${m.text()}`));
  for (const [name, path] of Object.entries(routes)) {
    const t0 = Date.now();
    await page.goto(base + path, { waitUntil: "networkidle" });
    await page.waitForTimeout(name === "run" ? 2500 : 800); // let the graph layout settle
    await page.screenshot({ path: `${out}/${sizeName}-${name}.png` });
    console.log(`${sizeName} ${name}: ${Date.now() - t0} ms`);
  }
  // one paper page, reached by clicking the first paper link on the report, if any
  await page.goto(base + routes.report, { waitUntil: "networkidle" });
  const link = page.locator(`a[href*="/runs/${runId}/paper/"]`).first();
  if (await link.count()) {
    await link.click();
    await page.waitForLoadState("networkidle");
    // wait for the source panel to resolve, then select the first claim (the demo beat:
    // its verbatim quote lights up inside the text ATLAS read)
    await page.waitForSelector("mark", { timeout: 20000 }).catch(() => {});
    const claim = page.locator("button[aria-pressed]").first();
    if (await claim.count()) await claim.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${out}/${sizeName}-paper.png` });
    console.log(`${sizeName} paper: ${page.url()}`);
  }
  await page.close();
}
await browser.close();
writeFileSync(`${out}/problems.txt`, problems.join("\n"));
console.log(problems.length ? `PROBLEMS:\n${problems.join("\n")}` : "no page/console errors");
