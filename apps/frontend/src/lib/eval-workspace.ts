/**
 * Evaluation workspace helpers. Hidden nav is not authorization.
 */

import { TERMINAL_SSE_EVENT_TYPES } from "./types/sse";

/**
 * Return whether `/api/meta` advertises the local Evaluation tab.
 *
 * @param meta - Handshake body, or null while loading.
 * @returns True only when the server flag is explicitly true.
 */
export function pdfEvalCapability(
  meta: { pdf_eval_workspace?: boolean } | null | undefined,
): boolean {
  return meta?.pdf_eval_workspace === true;
}

/**
 * Return whether citation overlap may run.
 *
 * Comparison before a terminal `completed` event is forbidden.
 *
 * @param terminal - Chat view terminal event, or null while streaming.
 * @returns True only after a completed paid run.
 */
export function citationCompareAllowed(terminal: string | null): boolean {
  return terminal === "completed";
}

/**
 * Return whether a case split forbids the AI test Run control.
 *
 * @param split - Case split label.
 * @returns True for holdout rows.
 */
export function holdoutCannotRun(split: string): boolean {
  return split === "holdout";
}

/**
 * Return the only field sent to the paid Ask protocol.
 *
 * Expected answers, facts, and gold IDs are omitted.
 *
 * @param question - Case question. Untrusted.
 * @returns `{ message }` only.
 */
export function evalAiRequestBody(question: string): { message: string } {
  return { message: question };
}

const TERMINAL = new Set<string>(TERMINAL_SSE_EVENT_TYPES);

/**
 * Return whether a chat run has reached any terminal event.
 *
 * @param terminal - Chat view terminal, or null.
 * @returns True for completed, cancelled, error, or partial.
 */
export function evalRunIsTerminal(terminal: string | null): boolean {
  return terminal !== null && TERMINAL.has(terminal);
}
