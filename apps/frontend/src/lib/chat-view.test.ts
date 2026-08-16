import { describe, expect, it } from "vitest";
import {
  applyAdmission,
  applySseFrame,
  createChatViewState,
  resumeAfterSequence,
} from "./chat-view";
import { parseSseBlock } from "./sse";

describe("chat view", () => {
  it("reuses the same idempotency key across retry", () => {
    const key = "22222222-2222-4222-8222-222222222222";
    const first = createChatViewState(key);
    const retried = createChatViewState(first.idempotencyKey);
    expect(retried.idempotencyKey).toBe(key);
  });

  it("applies token deltas and records sequence for resume", () => {
    let state = createChatViewState("k");
    state = applyAdmission(state, {
      run_id: "run-1",
      reservation_id: "res-1",
      route_family: "composite",
      reconnect: false,
    });
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 4\ndata: {"delta":"<script>x</script>"}'),
    );
    expect(state.answerText).toBe("<script>x</script>");
    expect(state.lastSequence).toBe(4);
    expect(resumeAfterSequence(state)).toBe(4);
  });

  it("logs unknown events and continues", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, parseSseBlock("event: future_metric\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 2\ndata: {"code":"temporal_graph_limitation"}'),
    );
    expect(state.diagnostics.unknownEvents).toEqual(["future_metric"]);
    expect(state.diagnostics.limitationCodes).toEqual([
      "temporal_graph_limitation",
    ]);
    expect(state.terminal).toBeNull();
  });

  it("freezes token deltas after a terminal event", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, parseSseBlock("event: completed\nid: 8\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 9\ndata: {"delta":"late"}'),
    );
    expect(state.answerText).toBe("");
    expect(state.terminal).toBe("completed");
    expect(state.lastSequence).toBe(9);
  });
});
