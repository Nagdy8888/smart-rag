/**
 * Map a live run stage to the one-line Ask status copy.
 */

import type { ChatViewState } from "../../lib/chat-view";

/**
 * Return the idle-hidden status line for an in-flight run.
 *
 * @param chat - Current view.
 * @returns Exactly one of Preparing…, Retrieving…, Generating…, Verifying…,
 *   or null when idle.
 */
export function runStatusLine(chat: ChatViewState): string | null {
  if (chat.terminal !== null || chat.runId === null) {
    return null;
  }
  const raw = (chat.stage ?? "").toLowerCase();
  if (raw.includes("verif")) {
    return "Verifying…";
  }
  if (raw.includes("generat") || raw.includes("answer")) {
    return "Generating…";
  }
  if (raw.includes("retriev") || raw.includes("search")) {
    return "Retrieving…";
  }
  return "Preparing…";
}
