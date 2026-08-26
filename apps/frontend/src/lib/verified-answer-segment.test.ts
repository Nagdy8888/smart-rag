import { describe, expect, it } from "vitest";
import { segmentVerifiedText } from "./verified-answer-segment";

const SAMPLES = [
  "مرحبا بالعالم",
  "cafe\u0301",
  "👨‍👩‍👧‍👦",
  "🇺🇸",
  "Hello\nworld",
  "See [1] and **bold**.",
  "السلام [2] 👨‍👩‍👧 end",
] as const;

describe("segmentVerifiedText", () => {
  it("joins back to the original string for mixed Unicode samples", () => {
    for (const sample of SAMPLES) {
      expect(segmentVerifiedText(sample).join("")).toBe(sample);
    }
  });

  it("returns no segments for empty text", () => {
    expect(segmentVerifiedText("")).toEqual([]);
  });

  it("does not split a combining mark away from its base", () => {
    const segments = segmentVerifiedText("e\u0301");
    expect(segments.join("")).toBe("e\u0301");
    expect(segments.some((part) => part === "\u0301")).toBe(false);
  });
});
