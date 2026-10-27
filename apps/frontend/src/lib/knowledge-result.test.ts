import { describe, expect, it } from "vitest";
import { parseKnowledgeResult } from "./knowledge-result";

describe("knowledge outcomes", () => {
  it("never invents support for legacy, malformed, or operational statuses", () => {
    for (const value of [null, {}, { outcome: "verification_unavailable", limitations: [] },
      { outcome: "supported", limitations: [42] }]) expect(parseKnowledgeResult(value)).toBeNull();
  });
  it("retains checked status and bounds additive limitations and uncovered parts", () => {
    const result = parseKnowledgeResult({ outcome: "partial", limitations: ["source_unreviewed"], unanswered_parts: ["Retention", 42] });
    expect(result).toEqual({ outcome: "partial", limitations: ["source_unreviewed"], unanswered_parts: ["Retention"] });
  });
});
