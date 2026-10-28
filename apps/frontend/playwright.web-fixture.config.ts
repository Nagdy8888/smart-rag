import { defineConfig } from "@playwright/test";

/** Separate server lifecycle so the standard unauthenticated suite stays strict. */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "web-quality-fixture.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:3010", browserName: "chromium" },
  webServer: [
    {
      command: "node tests/fixtures/auth-server.mjs",
      url: "http://127.0.0.1:3041/health",
      timeout: 15_000,
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --port 3010 --hostname 127.0.0.1",
      url: "http://127.0.0.1:3010/login",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        NEXT_PUBLIC_API_BASE_URL: "http://127.0.0.1:8000",
        NEXT_PUBLIC_SUPABASE_URL: "http://127.0.0.1:3041",
        NEXT_PUBLIC_SUPABASE_ANON_KEY: "fixture-anon-key",
      },
    },
  ],
});
