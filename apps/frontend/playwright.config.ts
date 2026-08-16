import { defineConfig } from "@playwright/test";

/**
 * Playwright configuration for the thin developer UI.
 *
 * CI quality gates currently assert the pinned runner version. Live JWT/SSE
 * journeys use a dedicated port so the Compose frontend on :3000 is not reused.
 * Browser Auth is local GoTrue, never the managed project URL from host `.env`.
 */
const LOCAL_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0";

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
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
      NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:54321",
      NEXT_PUBLIC_SUPABASE_ANON_KEY: LOCAL_ANON_KEY,
    },
  },
});
