/**
 * Derive a conversation title from the first user prompt.
 *
 * There is no title-update or LLM-title contract. The create body accepts
 * an optional `title` (max 512). This helper makes that title a compact
 * first-line summary of the question.
 */

/** API and rail display bound. Matches `ConversationCreateRequest`. */
export const CONVERSATION_TITLE_MAX = 80;

/**
 * Return a one-line title from the first prompt.
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
