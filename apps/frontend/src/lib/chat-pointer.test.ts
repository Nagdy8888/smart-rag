// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";
import {
  CHAT_RUN_POINTER_KEY,
  clearChatRunPointer,
  isActiveRunStatus,
  parseChatRunPointer,
  readChatRunPointer,
  writeChatRunPointer,
} from "./chat-pointer";

describe("chat run pointer", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores only conversation, run, and sequence", () => {
    writeChatRunPointer({
      conversationId: "conv-1",
      runId: "run-1",
      lastSequence: 4,
    });
    const raw = sessionStorage.getItem(CHAT_RUN_POINTER_KEY);
    expect(raw).not.toBeNull();
    expect(raw).not.toContain("token");
    expect(raw).not.toContain("answer");
    expect(parseChatRunPointer(raw)).toEqual({
      conversationId: "conv-1",
      runId: "run-1",
      lastSequence: 4,
    });
    expect(readChatRunPointer()).toEqual({
      conversationId: "conv-1",
      runId: "run-1",
      lastSequence: 4,
    });
  });

  it("ignores malformed payloads and extra secret fields", () => {
    expect(parseChatRunPointer("not-json")).toBeNull();
    expect(
      parseChatRunPointer(
        JSON.stringify({
          conversationId: "conv-1",
          runId: "run-1",
          lastSequence: 1,
          accessToken: "SECRET",
          answerText: "SECRET",
        }),
      ),
    ).toEqual({
      conversationId: "conv-1",
      runId: "run-1",
      lastSequence: 1,
    });
    expect(parseChatRunPointer(JSON.stringify({ runId: "run-1" }))).toBeNull();
  });

  it("clears the pointer and recognizes active statuses", () => {
    writeChatRunPointer({
      conversationId: "conv-1",
      runId: "run-1",
      lastSequence: 0,
    });
    clearChatRunPointer();
    expect(readChatRunPointer()).toBeNull();
    expect(isActiveRunStatus("pending")).toBe(true);
    expect(isActiveRunStatus("running")).toBe(true);
    expect(isActiveRunStatus("completed")).toBe(false);
  });
});
