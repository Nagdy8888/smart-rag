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

  it("ignores duplicate and older sequences", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 5\ndata: {"delta":"ok"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 5\ndata: {"delta":"dup"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 3\ndata: {"delta":"old"}'),
    );
    expect(state.answerText).toBe("ok");
    expect(state.lastSequence).toBe(5);
  });

  it("records route correction, deadline, and limitation codes from the catalog", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: route_correction\nid: 1\ndata: {"from_route":"hybrid","to_route":"combined","reason":"relationship"}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 2\ndata: {"code":"insufficient_evidence"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 3\ndata: {"code":"coverage_gap"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 4\ndata: {"code":"negation_unresolved"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 5\ndata: {"code":"media_limitation"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 6\ndata: {"code":"temporal_graph_limitation"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: limitation\nid: 7\ndata: {"code":"bm25_unavailable"}'),
    );
    state = applySseFrame(state, parseSseBlock("event: deadline\nid: 8\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock('event: partial\nid: 9\ndata: {"reason":"deadline"}'),
    );
    expect(state.diagnostics.requestedRoute).toBe("hybrid");
    expect(state.diagnostics.correctedRoute).toBe("combined");
    expect(state.diagnostics.effectiveRoute).toBe("combined");
    expect(state.diagnostics.limitationCodes).toEqual([
      "insufficient_evidence",
      "coverage_gap",
      "negation_unresolved",
      "media_limitation",
      "temporal_graph_limitation",
      "bm25_unavailable",
    ]);
    expect(state.stage).toBe("deadline");
    expect(state.terminal).toBe("partial");
  });

  it("keeps the answer when an unknown additive event is injected", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 1\ndata: {"delta":"Hi"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock("event: future_metric\nid: 2\ndata: {\"n\":1}"),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 3\ndata: {"delta":"!"}'),
    );
    expect(state.answerText).toBe("Hi!");
    expect(state.diagnostics.unknownEvents).toEqual(["future_metric"]);
    expect(state.terminal).toBeNull();
  });
});
