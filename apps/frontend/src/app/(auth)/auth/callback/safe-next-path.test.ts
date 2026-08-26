/**
 * Adversarial matrix for the Auth callback `next` gate.
 */

import { describe, expect, it } from "vitest";
import { safeNextPath } from "./safe-next-path";

const ORIGIN = "http://localhost:3000";

describe("safeNextPath", () => {
  it.each([
    ["/", "/"],
    ["/documents", "/documents"],
    ["/chat?run=1", "/chat?run=1"],
    ["/graph#node", "/graph#node"],
    ["/auth/reset", "/auth/reset"],
    [null, "/"],
    ["", "/"],
  ] as const)("keeps valid relative path %j", (raw, expected) => {
    expect(safeNextPath(raw, ORIGIN)).toBe(expected);
  });

  it.each([
    "https://evil.example",
    "http://evil.example/phish",
    "//evil.example",
    "/\\evil.example",
    "/\\\\evil.example",
    "%2f%2fevil.example",
    "%2F%2Fevil.example",
    "/%5cevil.example",
    "/%5Cevil.example",
    "/%2f%2fevil.example",
    "/documents/%2e%2e/%2f%2fevil.example",
    "https://localhost:3000/documents",
    "/login\r\nLocation: https://evil.example",
    "/login\n",
    "/ok%ZZ",
    "/%",
    "//user:pass@evil.example",
    "\\\\evil.example",
  ] as const)("rejects open-redirect form %j", (raw) => {
    expect(safeNextPath(raw, ORIGIN)).toBe("/");
  });

  it("rejects a parsed origin that differs from the request", () => {
    expect(safeNextPath("//localhost:3001", ORIGIN)).toBe("/");
    expect(safeNextPath("/documents", "https://other.example")).toBe(
      "/documents",
    );
    const parsed = new URL("/documents", "https://other.example");
    expect(parsed.origin).toBe("https://other.example");
    expect(safeNextPath("//other.example/documents", ORIGIN)).toBe("/");
  });

  it("does not treat same-origin absolute URLs as relative paths", () => {
    expect(safeNextPath(`${ORIGIN}/documents`, ORIGIN)).toBe("/");
  });
});
