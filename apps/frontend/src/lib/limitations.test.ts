import { describe, expect, it } from "vitest";
import { graphAclBlindnessCopy, graphLimitationDisplay } from "./graph-client";
import { graphNotReadyCopy, limitationCopy, limitationTone } from "./limitations";

describe("limitationCopy", () => {
  it("warns about source code syntax without claiming it was repaired", () => {
    const copy = limitationCopy("source_code_syntax_invalid");
    expect(copy).toContain("did not pass a Python syntax check");
    expect(copy).toContain("reproduced from the cited source");
    expect(copy).not.toContain("fixed");
  });
  it("does not claim an unavailable verifier checked the answer", () => {
    expect(limitationCopy("verification_unavailable")).toContain("was not released");
    expect(limitationCopy("verifier_skipped")).not.toContain("passed citation checks");
    expect(limitationCopy("verifier_skipped")).not.toContain("timed out");
  });
  it("uses signed historical-graph language", () => {
    expect(limitationCopy("insufficient_evidence")).toBe(
      "Company sources could not support an answer. Narrow the question and try again.",
    );
    expect(limitationCopy("insufficient_evidence")).not.toMatch(
      /Something went wrong/i,
    );
    expect(limitationCopy("temporal_graph_limitation")).toContain("Hybrid");
    expect(limitationCopy("bm25_unavailable")).toContain("dense plus exact");
    expect(limitationCopy("graph_outage")).toContain("relabeled to Hybrid");
  });

  it("covers GraphLimitationCode values without unauthorized counts", () => {
    expect(limitationCopy("graph_partial_readiness")).toContain("authorized");
    expect(limitationCopy("graph_acl_blindness")).toBe(
      "Some sources you cannot access are omitted.",
    );
    expect(limitationCopy("graph_acl_blindness")).not.toMatch(/\d/);
    expect(limitationCopy("graph_survival_below_threshold")).toContain("Hybrid");
    expect(limitationCopy("graph_filtered_dirty")).toContain("Hybrid");
    expect(limitationCopy("global_steering_only")).toContain("steering");
    expect(limitationCopy("graph_empty")).toContain("No authorized");
    expect(limitationCopy("graph_deadline")).toContain("deadline");
    expect(limitationCopy("graph_cancelled")).toContain("cancelled");
    expect(limitationCopy("retrievers_unbound")).toContain("not attached");
    expect(limitationCopy("retrievers_unbound")).toContain("not grounded");
  });

  it("keeps BM25 degrade and Graph Pending as warning, not danger", () => {
    expect(limitationTone("bm25_unavailable")).toBe("warning");
    expect(limitationTone("graph_pending")).toBe("warning");
    expect(limitationTone("graph_updating")).toBe("warning");
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

describe("ACL blindness display", () => {
  it("ignores count even when the server sent one", () => {
    const text = graphLimitationDisplay({
      code: "graph_acl_blindness",
      count: 99,
    });
    expect(text).toBe(graphAclBlindnessCopy());
    expect(text).not.toContain("99");
    expect(text.toLowerCase()).not.toContain("title");
  });
});
