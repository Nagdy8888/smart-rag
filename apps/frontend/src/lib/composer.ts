/**
 * Chat composer bounds from the FastAPI message ceiling.
 *
 * `smart_rag_core.settings` pins the user-message maximum at 16384 characters.
 */

/** Maximum composer length. Matches the backend user-message ceiling. */
export const COMPOSER_MAX_CHARS = 16384;

/**
 * Return whether the composer draft may be submitted.
 *
 * @param draft - Untrusted textarea value.
 * @returns True when trimmed text is non-empty and within the ceiling.
 */
export function composerDraftIsSendable(draft: string): boolean {
  const trimmed = draft.trim();
  return trimmed.length > 0 && trimmed.length <= COMPOSER_MAX_CHARS;
}
