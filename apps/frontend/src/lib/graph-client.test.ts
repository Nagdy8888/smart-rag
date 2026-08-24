import { describe, expect, it } from "vitest";
import {
  GRAPH_INSPECT_MAX_DEPTH,
  buildGraphInspectRequest,
  clampGraphInspectDepth,
  clampGraphSearchQuery,
  graphLimitationDisplay,
  graphSearchQueryIsRunnable,
  isGraphOutageLimitation,
  isGraphPendingLimitation,
  visibleInspectNodes,
} from "./graph-client";

describe("clampGraphInspectDepth", () => {
  it("clamps above 3 and below 1", () => {
    expect(clampGraphInspectDepth(9)).toBe(GRAPH_INSPECT_MAX_DEPTH);
    expect(clampGraphInspectDepth(0)).toBe(1);
    expect(clampGraphInspectDepth(2.9)).toBe(2);
    expect(clampGraphInspectDepth(Number.NaN)).toBe(3);
  });
});

describe("buildGraphInspectRequest", () => {
  it("caps entity keys at 12 and depth at 3", () => {
    const keys = Array.from({ length: 20 }, (_, index) => `ent-${String(index)}`);
    const body = buildGraphInspectRequest(keys, "doc-1", 99);
    expect(body.entity_keys).toHaveLength(12);
    expect(body.depth).toBe(3);
    expect(body.document_id).toBe("doc-1");
  });
});

describe("graphLimitationDisplay", () => {
  it("keeps Graph Pending distinct from ACL blindness without unauthorized counts", () => {
    expect(isGraphPendingLimitation("graph_pending")).toBe(true);
    expect(isGraphPendingLimitation("graph_acl_blindness")).toBe(false);
    expect(
      graphLimitationDisplay({ code: "graph_acl_blindness", count: 44 }),
    ).not.toContain("44");
    expect(
      graphLimitationDisplay({ code: "graph_pending", count: 2 }),
    ).toContain("not ready");
    expect(isGraphOutageLimitation("graph_outage")).toBe(true);
    expect(isGraphOutageLimitation("graph_acl_blindness")).toBe(false);
    expect(graphSearchQueryIsRunnable("  ")).toBe(false);
    expect(graphSearchQueryIsRunnable("acme")).toBe(true);
    expect(clampGraphSearchQuery("x".repeat(200)).length).toBe(128);
    expect(visibleInspectNodes(Array.from({ length: 201 }, (_, index) => index))).toHaveLength(
      200,
    );
  });
});
