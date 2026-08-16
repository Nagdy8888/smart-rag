import { describe, expect, it } from "vitest";
import { formatBm25Summary, formatGraphHandoffSummary } from "./ingestion-status";

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
