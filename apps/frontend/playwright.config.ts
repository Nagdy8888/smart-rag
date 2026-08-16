import { defineConfig } from "@playwright/test";

/**
 * Playwright configuration for the thin developer UI.
 *
 * CI quality gates currently assert the pinned runner version. Live auth/SSE
 * journeys require local FastAPI + Supabase and are documented as optional.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3000",
  },
  webServer: {
    command: "pnpm dev --port 3000 --hostname 127.0.0.1",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
