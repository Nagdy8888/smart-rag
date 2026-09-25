import { describe, expect, it } from "vitest";
import { applyProgressFrame, beginAgentGraph, emptyRunProgress } from "./run-progress";

describe("run progress reducer", () => {
  it("opens the agent graph before the first server frame and keeps one row", () => {
    const opened = beginAgentGraph(emptyRunProgress());
    expect(opened.lastSequence).toBe(0);
    expect(opened.items).toEqual([
      expect.objectContaining({
        key: "enforce_admission",
        phase: "started",
        firstSequence: 0,
      }),
    ]);
    const started = applyProgressFrame(
      opened,
      "status",
      { stage: "enforce_admission", status: "running", phase: "started" },
      1,
      false,
    );
    expect(started.items).toHaveLength(1);
    const closed = applyProgressFrame(
      started,
      "status",
      { stage: "enforce_admission", status: "admitted", phase: "completed" },
      2,
      false,
    );
    expect(closed.items[0]).toMatchObject({
      key: "enforce_admission",
      phase: "completed",
      outcome: "admitted",
    });
  });

  it("opens then closes a node row", () => {
    let progress = emptyRunProgress();
    progress = applyProgressFrame(
      progress,
      "status",
      { stage: "prepare_query", status: "running", phase: "started" },
      1,
      false,
    );
    progress = applyProgressFrame(
      progress,
      "status",
      { stage: "prepare_query", status: "prepared", phase: "completed" },
      2,
      false,
    );
    expect(progress.items).toHaveLength(1);
    expect(progress.items[0]).toMatchObject({
      kind: "node",
      key: "prepare_query",
      phase: "completed",
      outcome: "prepared",
      firstSequence: 1,
      lastSequence: 2,
    });
  });

  it("opens then fails a tool row", () => {
    let progress = emptyRunProgress();
    progress = applyProgressFrame(
      progress,
      "tool_progress",
      { tool_key: "export_csv", phase: "started" },
      3,
      false,
    );
    progress = applyProgressFrame(
      progress,
      "tool_progress",
      { tool_key: "export_csv", phase: "failed" },
      4,
      false,
    );
    expect(progress.items[0]).toMatchObject({
      kind: "tool",
      key: "export_csv",
      phase: "failed",
    });
  });

  it("ignores duplicate and replayed sequences", () => {
    let progress = emptyRunProgress();
    progress = applyProgressFrame(
      progress,
      "status",
      { stage: "load_memory", phase: "started" },
      5,
      false,
    );
    const replayed = applyProgressFrame(
      progress,
      "status",
      { stage: "load_memory", phase: "started" },
      5,
      false,
    );
    expect(replayed.items).toHaveLength(1);
    expect(replayed.lastSequence).toBe(5);
  });

  it("appends a completed item when no start exists", () => {
    const progress = applyProgressFrame(
      emptyRunProgress(),
      "status",
      { stage: "compile_plan", status: "planned" },
      2,
      false,
    );
    expect(progress.items[0]).toMatchObject({
      key: "compile_plan",
      phase: "completed",
      firstSequence: 2,
    });
  });

  it("does not invent skipped stages or disclosure-only tools", () => {
    let progress = emptyRunProgress();
    progress = applyProgressFrame(
      progress,
      "status",
      { stage: "general_scope", phase: "started" },
      1,
      false,
    );
    progress = applyProgressFrame(
      progress,
      "optional_tool_disclosure",
      { tool_keys: ["export_csv"] },
      2,
      false,
    );
    expect(progress.items.map((item) => item.key)).toEqual(["general_scope"]);
    expect(progress.items.some((item) => item.kind === "tool")).toBe(false);
  });

  it("marks verification complete and freezes after a terminal", () => {
    let progress = applyProgressFrame(
      emptyRunProgress(),
      "status",
      { stage: "verify_answer", status: "verified", phase: "completed" },
      8,
      false,
    );
    expect(progress.verificationCompleted).toBe(true);
    progress = applyProgressFrame(progress, "completed", {}, 9, false);
    const frozen = applyProgressFrame(
      progress,
      "status",
      { stage: "ghost_node", phase: "started" },
      10,
      true,
    );
    expect(frozen.items.some((item) => item.key === "ghost_node")).toBe(false);
    expect(frozen.lastSequence).toBe(10);
  });
});
