import { defineConfig } from "@playwright/test";

/**
 * Playwright configuration for the thin developer UI.
 *
 * CI quality gates currently assert the pinned runner version. Live JWT/SSE
 * journeys use a dedicated port so the Compose frontend on :3000 is not reused.
 * Browser Auth uses `NEXT_PUBLIC_SUPABASE_URL` from the environment (hosted
 * project). Missing values fall back to a non-network placeholder so non-live
 * specs still load.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:3010",
    browserName: "chromium",
  },
  webServer: {
    command: "pnpm dev --port 3010 --hostname 127.0.0.1",
    url: "http://127.0.0.1:3010",
    // CI always starts a fresh :3010. Local reuse avoids failing the
    // frontend tier when a leftover Playwright Next process is already bound.
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_SUPABASE_URL:
        process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://placeholder.supabase.co",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
    },
  },
});
