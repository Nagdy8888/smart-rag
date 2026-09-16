import { describe, expect, it } from "vitest";
import { createChatViewState } from "./chat-view";
import {
  overlaySettledTurns,
  snapshotSettledTurn,
  type SettledChatTurn,
} from "./chat-history";
import type { ConversationMessage } from "./types";

function msg(
  id: string,
  role: ConversationMessage["role"],
  content: string,
): ConversationMessage {
  return {
    message_id: id,
    role,
    content,
    created_at: "2026-09-09T12:00:00Z",
  };
}

describe("snapshotSettledTurn", () => {
  it("captures a verified live answer before the next send clears it", () => {
    const chat = {
      ...createChatViewState("k"),
      runId: "run-1",
      answerText: "Hello! How can I assist you today?",
    };
    expect(snapshotSettledTurn("hi", chat, "2026-09-09T12:01:00Z")).toEqual({
      runId: "run-1",
      question: "hi",
      answer: "Hello! How can I assist you today?",
      createdAt: "2026-09-09T12:01:00Z",
    });
  });

  it("ignores a live run with no verified tokens", () => {
    const chat = { ...createChatViewState("k"), answerText: "   " };
    expect(snapshotSettledTurn("hello", chat, "2026-09-09T12:01:00Z")).toBeNull();
  });
});

describe("overlaySettledTurns", () => {
  it("inserts the previous assistant after the persisted user row", () => {
    const turns: SettledChatTurn[] = [
      {
        runId: "run-1",
        question: "hi",
        answer: "Hello! How can I assist you today?",
        createdAt: "2026-09-09T12:01:00Z",
      },
    ];
    const overlay = overlaySettledTurns([msg("u1", "user", "hi")], turns);
    expect(overlay.map((item) => [item.role, item.content])).toEqual([
      ["user", "hi"],
      ["assistant", "Hello! How can I assist you today?"],
    ]);
    expect(overlay[1]?.run_id).toBe("run-1");
  });

  it("keeps later live answers when sending the next question", () => {
    const overlay = overlaySettledTurns(
      [msg("u1", "user", "hi"), msg("u2", "user", "hello"), msg("u3", "user", "hiiiiiiiiii")],
      [
        {
          runId: "run-1",
          question: "hi",
          answer: "Hello! How can I assist you today?",
          createdAt: "2026-09-09T12:01:00Z",
        },
        {
          runId: "run-2",
          question: "hello",
          answer: "Hello again.",
          createdAt: "2026-09-09T12:02:00Z",
        },
      ],
    );
    expect(overlay.map((item) => [item.role, item.content])).toEqual([
      ["user", "hi"],
      ["assistant", "Hello! How can I assist you today?"],
      ["user", "hello"],
      ["assistant", "Hello again."],
      ["user", "hiiiiiiiiii"],
    ]);
  });

  it("does not duplicate an assistant already returned by GET /messages", () => {
    const overlay = overlaySettledTurns(
      [
        msg("u1", "user", "hi"),
        msg("a1", "assistant", "Hello! How can I assist you today?"),
      ],
      [
        {
          runId: "run-1",
          question: "hi",
          answer: "Hello! How can I assist you today?",
          createdAt: "2026-09-09T12:01:00Z",
        },
      ],
    );
    expect(overlay).toHaveLength(2);
    expect(overlay[1]?.message_id).toBe("a1");
  });

  it("matches HTML-escaped persisted user text to the live question", () => {
    const overlay = overlaySettledTurns(
      [msg("u1", "user", "What&#x27;s up?")],
      [
        {
          runId: "run-1",
          question: "What's up?",
          answer: "Not much.",
          createdAt: "2026-09-09T12:01:00Z",
        },
      ],
    );
    expect(overlay[1]?.content).toBe("Not much.");
  });
});
