import { describe, expect, it } from "vitest";
import {
  CITATION_LOGICAL_END,
  CITATION_LOGICAL_FIXTURE_TEXT,
  CITATION_LOGICAL_START,
  highlightLogicalRange,
} from "./highlight-logical-range";

describe("highlightLogicalRange", () => {
  it("selects ACME by codepoint offsets 7–11 in the brief fixture", () => {
    const parts = highlightLogicalRange(
      CITATION_LOGICAL_FIXTURE_TEXT,
      CITATION_LOGICAL_START,
      CITATION_LOGICAL_END,
    );
    expect(Array.from(CITATION_LOGICAL_FIXTURE_TEXT).slice(7, 11).join("")).toBe(
      "ACME",
    );
    expect(parts.match).toBe("ACME");
    expect(parts.before).toBe("الشركة ");
    expect(parts.after).toBe(" وقعت العقد.");
    expect(`${parts.before}${parts.match}${parts.after}`).toBe(
      CITATION_LOGICAL_FIXTURE_TEXT,
    );
  });

  it("slices by code points when a UTF-16 index would miss", () => {
    const text = "👍 ACME";
    expect(text.slice(2, 6)).not.toBe("ACME");
    expect(highlightLogicalRange(text, 2, 6).match).toBe("ACME");
  });

  it("clamps out-of-range indexes and rejects non-strings", () => {
    expect(highlightLogicalRange("ab", -2, 8)).toEqual({
      before: "",
      match: "ab",
      after: "",
    });
    expect(highlightLogicalRange("ab", 4, 1)).toEqual({
      before: "ab",
      match: "",
      after: "",
    });
    expect(highlightLogicalRange({ html: "<em>" }, 0, 1)).toEqual({
      before: "",
      match: "",
      after: "",
    });
  });
});
