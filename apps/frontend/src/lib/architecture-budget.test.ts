/**
 * Physical-line and ownership budgets for extracted Ask modules.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

/**
 * Count physical lines including blanks and comments.
 *
 * @param relativePath - Path under `apps/frontend/src`.
 * @returns Line count.
 */
function physicalLines(relativePath: string): number {
  return readFileSync(join(ROOT, relativePath), "utf8")
    .replace(/\n$/, "")
    .split(/\r?\n/).length;
}

describe("architecture budgets", () => {
  it("keeps ChatApp and barrels within physical-line budgets", () => {
    expect(physicalLines("components/chat/chat-app.tsx")).toBeLessThanOrEqual(320);
    expect(physicalLines("lib/api.ts")).toBeLessThanOrEqual(100);
    expect(physicalLines("lib/types.ts")).toBeLessThanOrEqual(100);
    expect(physicalLines("components/chat/hooks/use-chat-run.ts")).toBeLessThanOrEqual(380);
    expect(physicalLines("components/chat/hooks/use-chat-resume.ts")).toBeLessThanOrEqual(320);
    expect(physicalLines("components/chat/hooks/use-chat-queries.ts")).toBeLessThanOrEqual(300);
    expect(physicalLines("lib/table-plan.ts")).toBeLessThanOrEqual(100);
    expect(physicalLines("lib/admin-bodies.ts")).toBeLessThanOrEqual(100);
    expect(physicalLines("components/tables/analysis-plan.tsx")).toBeLessThanOrEqual(200);
    expect(physicalLines("components/documents/document-library.tsx")).toBeLessThanOrEqual(300);
    expect(physicalLines("components/admin/curation-panel.tsx")).toBeLessThanOrEqual(150);
    expect(physicalLines("components/auth/auth-screens.tsx")).toBeLessThanOrEqual(100);
    expect(physicalLines("components/graph/graph-explorer.tsx")).toBeLessThanOrEqual(220);
  });

  it("keeps consumeSse ownership in one chat-run transport owner", () => {
    const chatApp = readFileSync(join(ROOT, "components/chat/chat-app.tsx"), "utf8");
    expect(chatApp).not.toContain("consumeSse");
    expect(chatApp).not.toContain("startOrResumeMessageStream");
    expect(chatApp).not.toContain("resumeEventStream");
    expect(chatApp.includes("fetch(")).toBe(false);
    const family = [
      "components/chat/hooks/use-chat-run.ts",
      "components/chat/hooks/use-chat-resume.ts",
      "components/chat/hooks/start-chat-send.ts",
    ]
      .map((relative) => readFileSync(join(ROOT, relative), "utf8"))
      .join("\n");
    expect(family).toContain("consumeSse");
  });
});
