/**
 * Keep completed live Ask turns visible until GET /messages contains them.
 */

import type { ChatViewState } from "./chat-view";
import { displayText } from "./safe-text";
import type { ConversationMessage } from "./types";

/** One locally settled question/answer pair from a finished live run. */
export type SettledChatTurn = {
  runId: string | null;
  question: string;
  answer: string;
  createdAt: string;
};

/**
 * Return whether two transcript strings are the same after HTML-entity decode.
 *
 * @param left - Persisted or live text.
 * @param right - Persisted or live text.
 * @returns True when both are non-empty and decode to the same string.
 */
function sameVisibleText(left: string, right: string): boolean {
  if (left === "" || right === "") {
    return false;
  }
  return displayText(left) === displayText(right);
}

/**
 * Snapshot a finished live run before `startNextChatRun` clears `answerText`.
 *
 * @param previousQuestion - Live composer question for that run.
 * @param previousChat - View still holding that run's verified tokens.
 * @param createdAt - ISO timestamp for the overlay assistant row.
 * @returns Turn to overlay, or null when either side is blank.
 */
export function snapshotSettledTurn(
  previousQuestion: string,
  previousChat: ChatViewState,
  createdAt: string,
): SettledChatTurn | null {
  const question = previousQuestion.trim();
  const answer = previousChat.answerText.trim();
  if (question === "" || answer === "") {
    return null;
  }
  return {
    runId: previousChat.runId,
    question,
    answer,
    createdAt,
  };
}

/**
 * Insert settled assistant rows that the server transcript has not caught up to.
 *
 * User rows from admit usually already exist. This only adds the matching
 * assistant after the first free matching user, or both rows when the user
 * row is also missing.
 *
 * @param messages - Oldest-first persisted transcript.
 * @param turns - Finished live turns in send order.
 * @returns Messages with missing assistants filled in. No duplicates.
 */
export function overlaySettledTurns(
  messages: readonly ConversationMessage[],
  turns: readonly SettledChatTurn[],
): ConversationMessage[] {
  const next = [...messages];
  for (const [index, turn] of turns.entries()) {
    const question = turn.question.trim();
    const answer = turn.answer.trim();
    if (question === "" || answer === "") {
      continue;
    }
    let insertAt = -1;
    for (let cursor = 0; cursor < next.length; cursor += 1) {
      const item = next[cursor];
      if (
        item === undefined ||
        item.role !== "user" ||
        !sameVisibleText(item.content, question)
      ) {
        continue;
      }
      const following = next[cursor + 1];
      if (
        following !== undefined &&
        following.role === "assistant" &&
        sameVisibleText(following.content, answer)
      ) {
        continue;
      }
      insertAt = cursor + 1;
      break;
    }
    const assistant: ConversationMessage = {
      message_id: `local:${turn.runId ?? String(index)}:assistant`,
      role: "assistant",
      content: answer,
      created_at: turn.createdAt,
      run_id: turn.runId,
      citation_count: 0,
      citations: [],
    };
    if (insertAt >= 0) {
      next.splice(insertAt, 0, assistant);
      continue;
    }
    const hasUser = next.some(
      (item) => item.role === "user" && sameVisibleText(item.content, question),
    );
    if (hasUser) {
      continue;
    }
    next.push(
      {
        message_id: `local:${turn.runId ?? String(index)}:user`,
        role: "user",
        content: question,
        created_at: turn.createdAt,
      },
      assistant,
    );
  }
  return next;
}
