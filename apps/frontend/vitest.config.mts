import { defineConfig } from "vitest/config";

/**
 * Vitest configuration for foundation-only frontend unit contracts.
 *
 * Tests run in Node because Packet 4 has no browser UI behavior to claim.
 */
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts"],
    passWithNoTests: false,
  },
});
