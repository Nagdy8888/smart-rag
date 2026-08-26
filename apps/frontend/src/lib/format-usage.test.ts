// @vitest-environment node

import { describe, expect, it } from "vitest";
import { formatRunTokenUsage, formatTokenCount, formatUsd } from "./format-usage";

describe("formatUsd", () => {
  it("formats 0.4 as $0.40", () => {
    expect(formatUsd(0.4)).toBe("$0.40");
  });

  it("formats numeric strings", () => {
    expect(formatUsd("1")).toBe("$1.00");
  });

  it("returns an em dash for non-finite input", () => {
    expect(formatUsd("nope")).toBe("—");
  });
});

describe("formatTokenCount", () => {
  it("groups thousands and suffixes tokens", () => {
    expect(formatTokenCount(1234)).toBe("1,234 tokens");
  });
});

describe("formatRunTokenUsage", () => {
  it("hides zero usage", () => {
    expect(formatRunTokenUsage(0, 0)).toBeNull();
  });

  it("groups prompt and completion counts", () => {
    expect(formatRunTokenUsage(1234, 88)).toBe("1,234 prompt · 88 completion");
  });
});
