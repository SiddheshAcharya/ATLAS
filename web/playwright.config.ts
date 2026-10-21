import { defineConfig } from "@playwright/test";

// Smoke tests against a running ATLAS server (`atlas serve`, which also serves web/dist).
//   npm run build && (cd .. && atlas serve) ; then in web/: npm run test:smoke
// ATLAS_BASE_URL and ATLAS_SMOKE_RUN_ID override the defaults below.
export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  retries: 0,
  workers: 1, // one server, embedded Qdrant: keep requests sequential
  use: {
    baseURL: process.env.ATLAS_BASE_URL ?? "http://127.0.0.1:8000",
    viewport: { width: 1920, height: 1080 },
  },
});
