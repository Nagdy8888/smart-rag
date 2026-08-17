/**
 * Consume a fetch SSE body into chat view state.
 *
 * Unknown frames are applied through `applySseFrame` (logged, not fatal).
 * One terminal freezes later token deltas.
 */

import {
  applySseFrame,
  type ChatViewState,
} from "./chat-view";
import { parseSseBuffer } from "./sse";

/**
 * Read SSE frames until abort, stream end, or a terminal event.
 *
 * @param response - `text/event-stream` GET body.
 * @param initial - Current view, including `runId` after admit.
 * @param signal - Abort from Cancel or a new send.
 * @param onState - Called after each applied frame.
 * @returns Final view. Does not start paid work.
 */
export async function consumeSse(
  response: Response,
  initial: ChatViewState,
  signal: AbortSignal,
  onState: (state: ChatViewState) => void,
): Promise<ChatViewState> {
  const reader = response.body?.getReader();
  if (!reader) {
    return initial;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let current = initial;
  try {
    while (!signal.aborted) {
      const chunk = await reader.read();
      if (chunk.done) {
        break;
      }
      buffer += decoder.decode(chunk.value, { stream: true });
      const parsed = parseSseBuffer(buffer);
      buffer = parsed.rest;
      for (const frame of parsed.frames) {
        current = applySseFrame(current, frame);
        onState(current);
        if (current.terminal !== null) {
          return current;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  return current;
}
