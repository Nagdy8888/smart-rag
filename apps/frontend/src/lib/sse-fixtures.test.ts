/**
 * Checked-in SSE fixtures stay synthetic and honor route-stage contracts.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const FIXTURE_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "../../tests/fixtures/sse",
);

const META = JSON.parse(
  readFileSync(join(FIXTURE_DIR, "route-progress.json"), "utf8"),
) as {
  leakage_marker: string;
  forbidden_substrings: string[];
  routes: Record<
    string,
    { file: string; required_stages: string[]; forbidden_stages: string[] }
  >;
};

/**
 * Read one fixture as text.
 *
 * @param fileName - File under `tests/fixtures/sse`.
 * @returns File contents.
 */
function readFixture(fileName: string): string {
  return readFileSync(join(FIXTURE_DIR, fileName), "utf8");
}

describe("checked-in SSE fixtures", () => {
  it("marks every route fixture as synthetic and leak-free", () => {
    for (const route of Object.values(META.routes)) {
      const body = readFixture(route.file);
      expect(body).toContain(META.leakage_marker);
      for (const forbidden of META.forbidden_substrings) {
        expect(body.toLowerCase()).not.toContain(forbidden.toLowerCase());
      }
      for (const stage of route.required_stages) {
        expect(body).toContain(`"stage":"${stage}"`);
      }
      for (const stage of route.forbidden_stages) {
        expect(body).not.toContain(`"stage":"${stage}"`);
      }
      if (body.includes('"stage":"verify_answer"')) {
        const verifyCompleted = body.indexOf(
          '"stage":"verify_answer","status":"verified"',
        );
        const firstToken = body.indexOf("event: token_delta");
        expect(verifyCompleted).toBeGreaterThan(-1);
        expect(firstToken).toBeGreaterThan(verifyCompleted);
      }
    }
  });
});
