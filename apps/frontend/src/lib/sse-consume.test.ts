/**
 * SSE consume abort and query_run_id isolation.
 */

import { describe, expect, it } from "vitest";
import { createChatViewState } from "./chat-view";
import { consumeSse, frameBelongsToCurrentRun } from "./sse-consume";

describe("frameBelongsToCurrentRun", () => {
  it("ignores frames named for a different query run", () => {
    expect(
      frameBelongsToCurrentRun(
        {
          event: "token_delta",
          id: "2",
          data: JSON.stringify({
            query_run_id: "run-other",
            delta: "nope",
          }),
        },
        "run-current",
      ),
    ).toBe(false);
  });

  it("applies frames for the current run and frames without a run id", () => {
    expect(
      frameBelongsToCurrentRun(
        {
          event: "token_delta",
          id: "2",
          data: JSON.stringify({ query_run_id: "run-current", delta: "ok" }),
        },
        "run-current",
      ),
    ).toBe(true);
    expect(
      frameBelongsToCurrentRun(
        { event: "heartbeat", id: "1", data: "{}" },
        "run-current",
      ),
    ).toBe(true);
  });
});

describe("consumeSse", () => {
  it("does not apply token deltas from a different query_run_id", async () => {
    const body = [
      "event: token_delta",
      "id: 1",
      `data: ${JSON.stringify({ query_run_id: "run-other", delta: "SECRET" })}`,
      "",
      "event: token_delta",
      "id: 2",
      `data: ${JSON.stringify({ query_run_id: "run-current", delta: "Hi" })}`,
      "",
      "",
    ].join("\n");
    const response = new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
    const initial = {
      ...createChatViewState("33333333-3333-4333-8333-333333333333"),
      runId: "run-current",
    };
    const states: string[] = [];
    const final = await consumeSse(
      response,
      initial,
      new AbortController().signal,
      (state) => {
        states.push(state.answerText);
      },
    );
    expect(final.answerText).toBe("Hi");
    expect(states.join("")).not.toContain("SECRET");
  });

  it("stops when the abort signal is already aborted", async () => {
    const response = new Response(
      'event: token_delta\ndata: {"delta":"late"}\n\n',
      {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      },
    );
    const controller = new AbortController();
    controller.abort();
    const initial = createChatViewState("33333333-3333-4333-8333-333333333333");
    const final = await consumeSse(
      response,
      initial,
      controller.signal,
      () => undefined,
    );
    expect(final.answerText).toBe("");
  });
});
