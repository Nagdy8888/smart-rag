/**
 * Derive a fallback conversation title from the first user prompt.
 *
 * `POST /conversations` still accepts an optional `title` (max 512) so the
 * rail can render immediately. After the first completed turn, the client
 * calls `POST /conversations/{id}/title` so the LLM can replace that
 * fallback with a short summary.
 */

/** API and rail display bound. Matches the LLM title contract. */
export const CONVERSATION_TITLE_MAX = 80;

/**
 * Return a one-line fallback title from the first prompt.
 *
 * @param message - Raw composer text.
 * @returns Compact title, or `"Chat"` when empty.
 */
export function conversationTitleFromPrompt(message: string): string {
  const compact = message.replace(/\s+/g, " ").trim();
  if (compact === "") {
    return "Chat";
  }
  if (compact.length <= CONVERSATION_TITLE_MAX) {
    return compact;
  }
  return `${compact.slice(0, CONVERSATION_TITLE_MAX - 1).trimEnd()}…`;
}

/**
 * Return whether the stored title is still a first-prompt fallback.
 *
 * @param title - Current API title.
 * @param firstUserText - First user message used at create time.
 * @returns True when an LLM title has not been stored yet.
 */
export function conversationTitleNeedsLlm(
  title: string | null,
  firstUserText: string,
): boolean {
  const current = (title ?? "").replace(/\s+/g, " ").trim();
  if (current === "" || current.toLowerCase() === "chat") {
    return true;
  }
  return current === conversationTitleFromPrompt(firstUserText);
}
