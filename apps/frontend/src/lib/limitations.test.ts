import { describe, expect, it } from "vitest";
import { graphNotReadyCopy, limitationCopy } from "./limitations";

describe("limitationCopy", () => {
  it("uses signed historical-graph language", () => {
    expect(limitationCopy("temporal_graph_limitation")).toContain("Hybrid");
  });
});

describe("graphNotReadyCopy", () => {
  it("never mentions restricted or ineligible counts", () => {
    const text = graphNotReadyCopy(3);
    expect(text).toBe(
      "3 relevant recent documents are not yet represented in the graph",
    );
    expect(text.toLowerCase()).not.toContain("restricted");
    expect(text.toLowerCase()).not.toContain("ineligible");
  });
});
