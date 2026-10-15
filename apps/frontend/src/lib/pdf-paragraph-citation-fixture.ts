/**
 * Shared AI Agents PDF citation fixture labels for unit and E2E tests.
 *
 * File page 25 is `page_index + 1`. Acrobat’s logical `page_label` is 12.
 */

/** Canonical chip text when the PDF label is 12. */
export const AI_AGENTS_CHIP_LABEL = "AI Agents · p. 12";

/** Drawer heading for the same logical page. */
export const AI_AGENTS_DRAWER_TITLE = "AI Agents — p. 12";

/** Exact supporting span persisted on file page 25. */
export const AI_AGENTS_UNIQUE_SPAN = "Refunds close in thirty calendar days.";

/** Sequential file page that must not replace the Acrobat label. */
export const AI_AGENTS_FORBIDDEN_FILE_PAGE = "PDF page 25";
