/**
 * Reload pointer for an in-flight Ask run. sessionStorage only; never tokens
 * or retrieved evidence.
 */

/** sessionStorage key for the active Ask run pointer. */
export const CHAT_RUN_POINTER_KEY = "smart-rag.chat-run-pointer";

/** Durable resume pointer. No answer text, citations, or tokens. */
export type ChatRunPointer = {
  conversationId: string;
  runId: string;
  lastSequence: number;
};

/**
 * Return whether a run status is still streamable.
 *
 * @param status - Durable `app.run_status` value.
 * @returns True for `pending` or `running`.
 */
export function isActiveRunStatus(status: string): boolean {
  return status === "pending" || status === "running";
}

/**
 * Parse a sessionStorage pointer. Extra keys are ignored.
 *
 * @param raw - Stored JSON, or null.
 * @returns Pointer, or null when missing or malformed.
 */
export function parseChatRunPointer(raw: string | null): ChatRunPointer | null {
  if (raw === null || raw === "") {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    const record = parsed as Record<string, unknown>;
    if (
      typeof record.conversationId !== "string" ||
      record.conversationId === "" ||
      typeof record.runId !== "string" ||
      record.runId === "" ||
      typeof record.lastSequence !== "number" ||
      !Number.isFinite(record.lastSequence)
    ) {
      return null;
    }
    return {
      conversationId: record.conversationId,
      runId: record.runId,
      lastSequence: Math.max(0, Math.trunc(record.lastSequence)),
    };
  } catch {
    return null;
  }
}

/**
 * Read the Ask pointer from sessionStorage.
 *
 * @param storage - sessionStorage, or null when unavailable.
 * @returns Pointer, or null.
 */
export function readChatRunPointer(
  storage: Pick<Storage, "getItem"> | null = defaultSessionStorage(),
): ChatRunPointer | null {
  if (storage === null) {
    return null;
  }
  try {
    return parseChatRunPointer(storage.getItem(CHAT_RUN_POINTER_KEY));
  } catch {
    return null;
  }
}

/**
 * Persist the Ask pointer. Never writes tokens or answer text.
 *
 * @param pointer - Conversation, run, and last SSE sequence.
 * @param storage - sessionStorage, or null when unavailable.
 */
export function writeChatRunPointer(
  pointer: ChatRunPointer,
  storage: Pick<Storage, "setItem"> | null = defaultSessionStorage(),
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.setItem(
      CHAT_RUN_POINTER_KEY,
      JSON.stringify({
        conversationId: pointer.conversationId,
        runId: pointer.runId,
        lastSequence: pointer.lastSequence,
      }),
    );
  } catch {
    return;
  }
}

/**
 * Clear the Ask pointer after a terminal, deleted, or foreign run.
 *
 * @param storage - sessionStorage, or null when unavailable.
 */
export function clearChatRunPointer(
  storage: Pick<Storage, "removeItem"> | null = defaultSessionStorage(),
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.removeItem(CHAT_RUN_POINTER_KEY);
  } catch {
    return;
  }
}

/**
 * Return sessionStorage when the browser exposes it.
 *
 * @returns sessionStorage, or null in non-browser tests without it.
 */
function defaultSessionStorage(): Storage | null {
  if (typeof sessionStorage === "undefined") {
    return null;
  }
  return sessionStorage;
}
