// @vitest-environment node

import { describe, expect, it } from "vitest";
import { conversationAgeGroup, formatRelativeTime } from "./relative-time";

const NOW = new Date(2026, 7, 25, 15, 0, 0);

/**
 * Build a local ISO string for the given calendar offset from `NOW`.
 *
 * @param daysAgo - Whole days before today.
 * @returns ISO timestamp.
 */
function daysAgoIso(daysAgo: number): string {
  const date = new Date(2026, 7, 25 - daysAgo, 10, 0, 0);
  return date.toISOString();
}

describe("formatRelativeTime", () => {
  it("uses RelativeTimeFormat inside seven days", () => {
    const formatted = formatRelativeTime(
      new Date(2026, 7, 25, 14, 0, 0).toISOString(),
      NOW,
    );
    expect(formatted).toMatch(/hour/i);
  });

  it("falls back to a short date after seven days", () => {
    expect(formatRelativeTime(daysAgoIso(24), NOW)).toMatch(/Aug|8/);
  });

  it("returns empty text for invalid input", () => {
    expect(formatRelativeTime("not-a-date", NOW)).toBe("");
  });
});

describe("conversationAgeGroup", () => {
  it("buckets today, yesterday, previous 7 days, and older", () => {
    expect(conversationAgeGroup(daysAgoIso(0), NOW)).toBe("Today");
    expect(conversationAgeGroup(daysAgoIso(1), NOW)).toBe("Yesterday");
    expect(conversationAgeGroup(daysAgoIso(5), NOW)).toBe("Previous 7 days");
    expect(conversationAgeGroup(daysAgoIso(40), NOW)).toBe("Older");
    expect(conversationAgeGroup(null, NOW)).toBe("Older");
  });
});
