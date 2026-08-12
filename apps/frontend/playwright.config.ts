import { defineConfig } from "@playwright/test";

/**
 * Playwright foundation configuration.
 *
 * Browser tests are enabled only when a later packet adds real user behavior;
 * Packet 4 verifies the pinned runner contract without claiming E2E coverage.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3000",
  },
});
