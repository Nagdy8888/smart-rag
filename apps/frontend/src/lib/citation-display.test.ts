import { describe, expect, it } from "vitest";
import { citationDisplayNumber, citationPageGroups } from "./citation-display";
import type { CitationResponse } from "./types";

const citation = (index: number, url: string): CitationResponse => ({
  citation_id: `c-${index}`, citation_index: index, chunk_id: null,
  source_kind: "web", source_unavailable: false, provenance: { url },
});

describe("citation display identity", () => {
  it("starts at one even for sparse historical indices without mutating them", () => {
    const citations = [citation(9, "https://example.org/a"), citation(0, "https://example.org/b")];
    expect(citationDisplayNumber(citations[1]!, citations)).toBe(1);
    expect(citationDisplayNumber(citations[0]!, citations)).toBe(2);
    expect(citations.map(item => item.citation_index)).toEqual([9, 0]);
  });
  it("groups page fragments but preserves every supporting-passage identity", () => {
    const citations = [citation(0, "https://example.org/a#one"), citation(1, "https://example.org/a#two"), citation(2, "https://example.org/b")];
    const groups = citationPageGroups(citations);
    expect(groups.map(group => group.length)).toEqual([2, 1]);
    expect(groups[0]?.map(item => item.citation_id)).toEqual(["c-0", "c-1"]);
  });
});
