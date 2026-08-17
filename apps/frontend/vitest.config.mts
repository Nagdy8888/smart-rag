import { defineConfig } from "vitest/config";

/**
 * Vitest configuration for Node unit contracts and jsdom component tests.
 *
 * Component files opt into jsdom with `// @vitest-environment jsdom`.
 * Lib tests stay on Node so existing fetch/SSE contracts keep their
 * environment.
 */
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    environment: "node",
    passWithNoTests: false,
  },
});
