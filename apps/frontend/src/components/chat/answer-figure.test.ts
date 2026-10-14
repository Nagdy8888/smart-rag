import { describe, expect, it } from "vitest";
import { splitFigureMark } from "./answer-figure";

describe("splitFigureMark", () => {
  it("keeps a stored figure id and drops the mark from the caption", () => {
    const split = splitFigureMark(
      "Rates plot [[figure:abc123]]",
    );
    expect(split.figureId).toBe("abc123");
    expect(split.prose).toBe("Rates plot");
  });

  it("ignores a remote image address written as prose", () => {
    const split = splitFigureMark("See https://example.test/plot.png");
    expect(split.figureId).toBeNull();
    expect(split.prose).toContain("https://example.test/plot.png");
  });
});
