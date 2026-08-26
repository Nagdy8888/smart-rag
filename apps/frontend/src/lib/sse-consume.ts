/**
 * Consume a fetch SSE body into chat view state.
 *
 * Unknown frames are applied through `applySseFrame` (logged, not fatal).
 * One terminal freezes later token deltas. Frames whose `query_run_id` or
 * `run_id` does not match the current view are ignored.
 */

import {
  applySseFrame,
  type ChatViewState,
} from "./chat-view";
import { parseSseBuffer, parseSsePayload, type SseFrame } from "./sse";

/**
 * Return whether a fetch rejection is an abort.
 *
 * @param error - Rejection value.
 * @returns True for `AbortError`.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Return whether an SSE frame belongs to the in-view run.
 *
 * Frames without a run id always apply (schema, heartbeats). A mismatched
 * `query_run_id` or `run_id` is dropped so a stale stream cannot mutate
 * the current chat.
 *
 * @param frame - Parsed SSE frame.
 * @param runId - Current view `runId`, or null before admission.
 * @returns False when the frame names a different run.
 */
export function frameBelongsToCurrentRun(
  frame: SseFrame,
  runId: string | null,
): boolean {
  if (runId === null) {
    return true;
  }
  const payload = parseSsePayload(frame.data);
  const frameRunId = payload.query_run_id ?? payload.run_id;
  if (typeof frameRunId !== "string" || frameRunId === "") {
    return true;
  }
  return frameRunId === runId;
}

/**
 * Read SSE frames until abort, stream end, or a terminal event.
 *
 * @param response - `text/event-stream` GET body.
 * @param initial - Current view, including `runId` after admit.
 * @param signal - Abort from Cancel or a new send. Honored on the reader
 *   and on `AbortError` from `reader.read()`.
 * @param onState - Called once per `reader.read()` batch, or at terminal.
 * @param onCursor - Optional. Called when an accepted batch advances sequence,
 *   including heartbeat-only batches. Does not imply a React publication.
 * @returns Final view. Does not start paid work.
 */
export async function consumeSse(
  response: Response,
  initial: ChatViewState,
  signal: AbortSignal,
  onState: (state: ChatViewState) => void,
  onCursor?: (lastSequence: number) => void,
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
      const sequenceBefore = current.lastSequence;
      let sawVisibleFrame = false;
      for (const frame of parsed.frames) {
        if (!frameBelongsToCurrentRun(frame, current.runId)) {
          continue;
        }
        current = applySseFrame(current, frame);
        if (frame.event !== "heartbeat") {
          sawVisibleFrame = true;
        }
        if (current.terminal !== null) {
          onState(current);
          onCursor?.(current.lastSequence);
          return current;
        }
      }
      if (current.lastSequence !== sequenceBefore) {
        onCursor?.(current.lastSequence);
      }
      if (sawVisibleFrame) {
        onState(current);
      }
    }
  } catch (error) {
    if (signal.aborted || isAbortError(error)) {
      return current;
    }
    throw error;
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  return current;
}
