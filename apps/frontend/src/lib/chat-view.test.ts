import { describe, expect, it } from "vitest";
import {
  addChatTokens,
  applyAdmission,
  applySseFrame,
  chatCostTotal,
  chatTokenTotals,
  createChatViewState,
  hasKeptAnswer,
  resumeAfterSequence,
  shouldShowChatFailureBanner,
  startNextChatRun,
} from "./chat-view";
import { parseSseBlock } from "./sse";

/**
 * Build a verify-complete status frame so later token_delta events are legal.
 *
 * @param id - Persisted sequence.
 * @returns Parsed SSE frame.
 */
function verifyFrame(id: number) {
  return parseSseBlock(
    `event: status\nid: ${String(id)}\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}`,
  );
}

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
      requested_search_scope: "company_documents",
    });
    expect(state.requestedSearchScope).toBe("company_documents");
    state = applySseFrame(state, verifyFrame(3));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 4\ndata: {"delta":"<script>x</script>"}'),
    );
    expect(state.answerText).toBe("<script>x</script>");
    expect(state.lastSequence).toBe(4);
    expect(resumeAfterSequence(state)).toBe(4);
  });

  it("records prompt and completion tokens from usage events", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: usage\nid: 2\ndata: {"prompt_tokens":1234,"completion_tokens":88,"cost_usd":0.48}',
      ),
    );
    expect(state.diagnostics.promptTokens).toBe(1234);
    expect(state.diagnostics.completionTokens).toBe(88);
    expect(state.diagnostics.costUsd).toBe(0.48);
    expect(chatTokenTotals(state)).toEqual({
      promptTokens: 1234,
      completionTokens: 88,
    });
    expect(chatCostTotal(state)).toBe(0.48);
  });

  it("carries conversation totals across questions and title usage", () => {
    let state = createChatViewState("first");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: usage\nid: 2\ndata: {"prompt_tokens":12506,"completion_tokens":501,"cost_usd":0.4}',
      ),
    );
    state = addChatTokens(state, 700, 74);
    expect(chatTokenTotals(state)).toEqual({
      promptTokens: 13206,
      completionTokens: 575,
    });
    expect(chatCostTotal(state)).toBe(0.4);
    const next = startNextChatRun(state, "second");
    expect(next.diagnostics.promptTokens).toBe(0);
    expect(next.diagnostics.costUsd).toBeNull();
    expect(next.chatPromptTokens).toBe(13206);
    expect(next.chatCompletionTokens).toBe(575);
    expect(next.chatCostUsd).toBe(0.4);
    const second = applySseFrame(
      next,
      parseSseBlock(
        'event: usage\nid: 1\ndata: {"prompt_tokens":258,"completion_tokens":32}',
      ),
    );
    expect(chatTokenTotals(second)).toEqual({
      promptTokens: 13464,
      completionTokens: 607,
    });
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
    state = applySseFrame(state, verifyFrame(6));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 7\ndata: {"delta":"Hi"}'),
    );
    state = applySseFrame(state, parseSseBlock("event: completed\nid: 8\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 9\ndata: {"delta":"late"}'),
    );
    expect(state.answerText).toBe("Hi");
    expect(state.terminal).toBe("completed");
    expect(state.lastSequence).toBe(9);
  });

  it("treats completed without answer or refusal as a protocol failure", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, parseSseBlock("event: completed\nid: 8\ndata: {}"));
    expect(state.terminal).toBe("error");
    expect(state.status).toBe("empty_answer");
    expect(state.failure).toEqual({ kind: "protocol", detail: "empty_answer" });
  });

  it("ignores duplicate and older sequences", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, verifyFrame(4));
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
    expect(state.failure).toBeNull();
    expect(shouldShowChatFailureBanner(state)).toBe(false);
  });

  it("treats deadline_exhausted partial as a non-failure terminal", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, parseSseBlock("event: deadline\nid: 1\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock('event: partial\nid: 2\ndata: {"reason":"deadline_exhausted"}'),
    );
    expect(state.stage).toBe("deadline");
    expect(state.terminal).toBe("partial");
    expect(state.status).toBe("deadline_exhausted");
    expect(state.failure).toBeNull();
    expect(shouldShowChatFailureBanner(state)).toBe(false);
  });

  it("keeps insufficient evidence as a graceful partial, not a protocol failure", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: status\nid: 1\ndata: {"stage":"generate_answer","status":"insufficient_evidence","phase":"completed"}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: status\nid: 2\ndata: {"stage":"verify_answer","status":"insufficient_evidence","phase":"completed"}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: token_delta\nid: 3\ndata: {"delta":"Company sources could not support an answer. Narrow the question and try again."}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: limitation\nid: 4\ndata: {"code":"insufficient_evidence"}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: partial\nid: 5\ndata: {"reason":"insufficient_evidence"}',
      ),
    );
    expect(state.answerText).toContain("Company sources could not support");
    expect(state.terminal).toBe("partial");
    expect(state.status).toBe("insufficient_evidence");
    expect(state.failure).toBeNull();
    expect(state.diagnostics.limitationCodes).toEqual(["insufficient_evidence"]);
    expect(shouldShowChatFailureBanner(state)).toBe(false);
  });

  it("keeps the first terminal when a later error arrives", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, verifyFrame(1));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 2\ndata: {"delta":"Hi"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: partial\nid: 3\ndata: {"reason":"verified_partial"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: error\nid: 4\ndata: {"code":"run_failed"}'),
    );
    expect(state.answerText).toBe("Hi");
    expect(state.terminal).toBe("partial");
    expect(state.failure).toBeNull();
    expect(hasKeptAnswer(state)).toBe(true);
    expect(shouldShowChatFailureBanner(state)).toBe(false);
  });

  it("does not open a failure banner when error arrives after tokens", () => {
    let state = createChatViewState("k");
    state = applyAdmission(state, {
      run_id: "1271314a-dc2a-46b7-bff1-b4c630d78415",
      reservation_id: "res-1",
      route_family: "hybrid",
      reconnect: false,
    });
    state = applySseFrame(state, verifyFrame(1));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 2\ndata: {"delta":"Hi"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: error\nid: 3\ndata: {"code":"run_failed"}'),
    );
    expect(state.terminal).toBe("error");
    expect(state.failure).toBeNull();
    expect(shouldShowChatFailureBanner(state)).toBe(false);
  });

  it("opens a failure banner only when error has no kept tokens", () => {
    let state = createChatViewState("k");
    state = applyAdmission(state, {
      run_id: "run-empty",
      reservation_id: "res-1",
      route_family: "hybrid",
      reconnect: false,
    });
    state = applySseFrame(
      state,
      parseSseBlock('event: error\nid: 1\ndata: {"code":"run_failed"}'),
    );
    expect(state.terminal).toBe("error");
    expect(state.failure).toEqual({ kind: "protocol", detail: "run_failed" });
    expect(shouldShowChatFailureBanner(state)).toBe(true);
  });

  it("keeps the answer when an unknown additive event is injected", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, verifyFrame(1));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 2\ndata: {"delta":"Hi"}'),
    );
    state = applySseFrame(
      state,
      parseSseBlock("event: future_metric\nid: 3\ndata: {\"n\":1}"),
    );
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 4\ndata: {"delta":"!"}'),
    );
    expect(state.answerText).toBe("Hi!");
    expect(state.diagnostics.unknownEvents).toEqual(["future_metric"]);
    expect(state.terminal).toBeNull();
  });

  it("stores additive answer origin without inferring it from the route", () => {
    let state = createChatViewState("k");
    state = applyAdmission(state, {
      run_id: "run-1",
      reservation_id: "res-1",
      route_family: "hybrid",
      reconnect: false,
    });
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: answer_origin\nid: 1\ndata: {"origin":"general_knowledge"}',
      ),
    );
    expect(state.answerOrigin).toBe("general_knowledge");
    expect(state.clarificationRequired).toBe(false);
    expect(state.diagnostics.effectiveRoute).toBe("hybrid");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: answer_origin\nid: 2\ndata: {"origin":"ambiguous"}',
      ),
    );
    expect(state.answerOrigin).toBe("ambiguous");
    expect(state.clarificationRequired).toBe(true);
  });

  it("tolerates unknown origin payloads and isolates XSS text", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: answer_origin\nid: 1\ndata: {"origin":"<script>x</script>"}',
      ),
    );
    expect(state.answerOrigin).toBe("<script>x</script>");
    expect(state.clarificationRequired).toBe(false);
    expect(state.terminal).toBeNull();
  });

  it("records hidden stray citations when origin is not company documents", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: citation_preview\nid: 1\ndata: {"citation_ids":["cite-1","cite-2"]}',
      ),
    );
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: answer_origin\nid: 2\ndata: {"origin":"user_supplied_text"}',
      ),
    );
    expect(state.diagnostics.citationIds).toEqual(["cite-1", "cite-2"]);
    expect(state.diagnostics.strayCitationsHidden).toBe(2);
  });

  it("counts heartbeats and records cancelled as the terminal", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, parseSseBlock("event: heartbeat\nid: 1\ndata: {}"));
    state = applySseFrame(state, parseSseBlock("event: heartbeat\nid: 2\ndata: {}"));
    state = applySseFrame(
      state,
      parseSseBlock("event: cancelled\nid: 3\ndata: {}"),
    );
    expect(state.diagnostics.heartbeatCount).toBe(2);
    expect(state.terminal).toBe("cancelled");
  });

  it("fails closed on token_delta before verification", () => {
    let state = createChatViewState("k");
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 1\ndata: {"delta":"SECRET_DRAFT"}'),
    );
    expect(state.answerText).toBe("");
    expect(state.failure).toEqual({
      kind: "protocol",
      detail: "unverified_token_delta",
    });
  });

  it("appends token_delta immediately after verify completion", () => {
    let state = createChatViewState("k");
    state = applySseFrame(state, verifyFrame(1));
    state = applySseFrame(
      state,
      parseSseBlock('event: token_delta\nid: 2\ndata: {"delta":"PUBLIC_FINAL"}'),
    );
    expect(state.progress.verificationCompleted).toBe(true);
    expect(state.answerText).toBe("PUBLIC_FINAL");
    expect(state.failure).toBeNull();
  });

  it("records BM25, LightRAG, ACL, pending, and summary limitation codes", () => {
    let state = createChatViewState("k");
    const codes = [
      "bm25_unavailable",
      "graph_outage",
      "graph_pending",
      "graph_acl_blindness",
      "coverage_gap",
      "global_steering_only",
    ];
    codes.forEach((code, index) => {
      state = applySseFrame(
        state,
        parseSseBlock(
          `event: limitation\nid: ${String(index + 1)}\ndata: {"code":"${code}"}`,
        ),
      );
    });
    state = applySseFrame(
      state,
      parseSseBlock(
        'event: citation_preview\nid: 20\ndata: {"citation_ids":["cite-1"],"snippet":"SECRET"}',
      ),
    );
    expect(state.diagnostics.limitationCodes).toEqual(codes);
    expect(state.diagnostics.citationIds).toEqual(["cite-1"]);
    expect(JSON.stringify(state.diagnostics)).not.toContain("SECRET");
  });
});
