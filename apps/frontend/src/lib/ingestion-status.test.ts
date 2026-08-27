import { describe, expect, it } from "vitest";
import {
  compactIngestionPills,
  formatBm25Summary,
  formatGraphHandoffSummary,
  bm25DetailRows,
  ingestionJobKindLabel,
  ingestionJobStatusLabel,
  ingestionStatusLabel,
  ingestionStatusTone,
  isOpenIngestionJob,
} from "./ingestion-status";

describe("formatBm25Summary", () => {
  it("renders index lag and queue counts without claiming readiness", () => {
    const text = formatBm25Summary({
      active_index_version: null,
      index_schema_version: null,
      lag_seconds: 12.5,
      pending: 1,
      processing: 0,
      failed: 2,
      dead_letter: 0,
      retry_attempts: 3,
      verified_at: null,
    });
    expect(text).toContain("index=none");
    expect(text).toContain("lag=12.5s");
    expect(text).toContain("failed=2");
    expect(text.toLowerCase()).not.toContain("ready");
  });
});

describe("formatGraphHandoffSummary", () => {
  it("shows handoff job counts without treating upload as graph ready", () => {
    const text = formatGraphHandoffSummary({
      pending: 4,
      processing: 0,
      completed: 0,
      failed: 0,
      dead_letter: 0,
    });
    expect(text).toBe(
      "pending=4 processing=0 completed=0 failed=0 dead_letter=0",
    );
  });
});

describe("ingestionStatusLabel", () => {
  it("labels Graph Pending distinctly from failed and does not invent quarantine HTTP", () => {
    expect(ingestionStatusLabel("graph_pending")).toBe("Graph pending");
    expect(ingestionStatusLabel("hybrid_ready")).toBe("Search ready");
    expect(ingestionStatusLabel("deletion_pending")).toBe("Deletion pending");
    expect(ingestionStatusLabel("scanning")).toBe("Scanning");
    expect(ingestionStatusLabel("parsing")).toBe("Parsing");
    expect(ingestionStatusLabel("failed")).toBe("Failed");
    expect(ingestionStatusTone("graph_pending")).toBe("warning");
    expect(ingestionStatusTone("failed")).toBe("danger");
    expect(ingestionStatusLabel("abandoned")).toBe("abandoned");
    expect(ingestionStatusLabel("expired")).toBe("expired");
    expect(ingestionStatusLabel("oversize")).toBe("oversize");
  });

  it("maps compact list pills without inventing Graph Ready from upload", () => {
    expect(compactIngestionPills("uploaded")).toEqual({
      search: { label: "Uploaded", tone: "warning" },
      graph: null,
    });
    expect(compactIngestionPills("hybrid_ready").search?.label).toBe("Search ready");
    expect(compactIngestionPills("hybrid_ready").graph).toBeNull();
    expect(compactIngestionPills("graph_ready").graph?.label).toBe("Graph ready");
    expect(compactIngestionPills("graph_pending").graph?.label).toBe("Graph pending");
    expect(compactIngestionPills("graph_ineligible").graph?.label).toBe(
      "Graph ineligible",
    );
  });
});

describe("ingestion detail rows", () => {
  it("skips idle BM25 none/zero rows and labels jobs", () => {
    expect(
      bm25DetailRows({
        active_index_version: null,
        index_schema_version: null,
        lag_seconds: null,
        pending: 0,
        processing: 0,
        failed: 0,
        dead_letter: 0,
        retry_attempts: 0,
        verified_at: null,
      }),
    ).toEqual([]);
    expect(
      bm25DetailRows({
        active_index_version: 2,
        index_schema_version: "v1",
        lag_seconds: 0,
        pending: 0,
        processing: 0,
        failed: 1,
        dead_letter: 0,
        retry_attempts: 0,
        verified_at: null,
      }),
    ).toEqual([
      { label: "Search index", value: "Version 2" },
      { label: "Search index failed", value: "1" },
    ]);
    expect(ingestionJobKindLabel("hybrid_index")).toBe("Search indexing");
    expect(ingestionJobStatusLabel("dead_letter")).toBe("Needs retry");
    expect(isOpenIngestionJob("completed")).toBe(false);
    expect(isOpenIngestionJob("failed")).toBe(true);
  });
});
