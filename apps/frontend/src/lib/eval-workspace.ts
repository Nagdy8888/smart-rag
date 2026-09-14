/**
 * Evaluation workspace helpers. Hidden nav is not authorization.
 */

import { isOwnerOrAdmin } from "./roles";
import { TERMINAL_SSE_EVENT_TYPES } from "./types/sse";

/** Maximum gold citations suggested from Ask. */
export const QUIZ_MAX_GOLD_CHUNKS = 3;

/** Retention copy shown beside Save to quiz. */
export const QUIZ_RETENTION_DISCLOSURE =
  "Deleting this chat does not delete the saved quiz case.";

/** Score control copy. Citation overlap is never official Recall@10. */
export const QUIZ_SCORE_NOT_RECALL_LABEL = "not Recall@10";

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
 * Return whether Ask should show Save to quiz.
 *
 * Convenience only. FastAPI still 403s members and viewers.
 *
 * @param role - `GET /me` role.
 * @param meta - Handshake body, or null while loading.
 * @returns True for owner/admin when the workspace capability is on.
 */
export function showSaveToQuizConvenience(
  role: string | undefined,
  meta: { pdf_eval_workspace?: boolean } | null | undefined,
): boolean {
  return isOwnerOrAdmin(role) && pdfEvalCapability(meta);
}

/**
 * Normalize a question the same way hosted duplicate detection does.
 *
 * @param question - Untrusted question text.
 * @returns Lowercase alphanumeric tokens separated by spaces.
 */
export function normalizeEvalQuestion(question: string): string {
  return question.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/**
 * Return whether Score this answer may run for a selected saved case.
 *
 * Newly saved drafts from this run cannot score their creating run.
 * The selected case must already be approved and the normalized
 * questions must match. Citation overlap is not Recall@10.
 *
 * @param input - Selected case, current run question, and create set.
 * @returns Allowed flag and a stable disabled reason.
 */
export function quizScoreDecision(input: {
  terminal: string | null;
  selectedCaseId: string | null;
  reviewStatus: string;
  humanApproved: boolean;
  selectedQuestion: string;
  currentQuestion: string;
  createdFromThisRun: ReadonlySet<string>;
}): { allowed: boolean; reason: string } {
  if (!citationCompareAllowed(input.terminal)) {
    return {
      allowed: false,
      reason: "Score this answer after the current run completes. not Recall@10",
    };
  }
  if (input.selectedCaseId === null) {
    return {
      allowed: false,
      reason:
        "Select a pre-existing approved case whose question matches. not Recall@10",
    };
  }
  if (input.createdFromThisRun.has(input.selectedCaseId)) {
    return {
      allowed: false,
      reason:
        "Newly saved drafts cannot score the run that created them. not Recall@10",
    };
  }
  const approved =
    input.humanApproved || input.reviewStatus === "approved";
  if (!approved) {
    return {
      allowed: false,
      reason:
        "Score this answer only for a pre-existing approved case. not Recall@10",
    };
  }
  if (
    normalizeEvalQuestion(input.selectedQuestion) !==
    normalizeEvalQuestion(input.currentQuestion)
  ) {
    return {
      allowed: false,
      reason:
        "Score this answer only when the saved question matches. not Recall@10",
    };
  }
  return { allowed: true, reason: "" };
}

/**
 * Toggle a gold chunk suggestion without exceeding three IDs.
 *
 * @param selected - Current unique chunk IDs.
 * @param chunkId - Citation chunk to add or remove.
 * @returns Next unique list, capped at three.
 */
export function toggleQuizGoldChunk(
  selected: readonly string[],
  chunkId: string,
): { next: string[]; blocked: boolean } {
  if (chunkId === "") {
    return { next: [...selected], blocked: false };
  }
  if (selected.includes(chunkId)) {
    return {
      next: selected.filter((item) => item !== chunkId),
      blocked: false,
    };
  }
  if (selected.length >= QUIZ_MAX_GOLD_CHUNKS) {
    return { next: [...selected], blocked: true };
  }
  return { next: [...selected, chunkId], blocked: false };
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

/** First page size for Admin case summaries. */
export const EVAL_LIST_PAGE_SIZE = 20;

/** Maximum accumulated Admin case rows. */
export const EVAL_LIST_MAX_ITEMS = 60;

/** Bounded gold-preview character cap. */
export const EVAL_PASSAGE_PREVIEW_CHARS = 240;

/** Client-side gold-state filter. SQL does not filter `gold_stale`. */
export type EvalGoldStateFilter = "all" | "current" | "stale";

/**
 * Filter accumulated summaries by gold freshness.
 *
 * @param items - Accumulated list rows.
 * @param goldState - Client-side gold filter.
 * @returns Filtered copy. Never requests `split=holdout`.
 */
export function filterEvalCasesByGoldState<
  T extends { gold_stale: boolean },
>(items: readonly T[], goldState: EvalGoldStateFilter): T[] {
  if (goldState === "stale") {
    return items.filter((item) => item.gold_stale);
  }
  if (goldState === "current") {
    return items.filter((item) => !item.gold_stale);
  }
  return [...items];
}

/**
 * Human list label that does not require a UUID.
 *
 * @param item - Summary or detail labels.
 * @returns Query class, split, and review status.
 */
export function evalCaseListLabel(item: {
  query_class: string;
  split: string;
  review_status: string;
  human_approved: boolean;
}): string {
  const review =
    item.review_status || (item.human_approved ? "approved" : "draft");
  return `${item.query_class} · ${item.split} · ${review}`;
}

/**
 * Bound an untrusted passage preview for the gold picker.
 *
 * @param raw - Passage text. Hostile.
 * @param max - Maximum characters, default 240.
 * @returns Trimmed preview. Render through `UserText`.
 */
export function boundedPassagePreview(
  raw: string,
  max = EVAL_PASSAGE_PREVIEW_CHARS,
): string {
  const trimmed = raw.trim();
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max)}…`;
}

/**
 * Page caption from a locator or current passage.
 *
 * @param input - Optional page label and PDF page number.
 * @returns Visible caption. Never a chunk UUID alone.
 */
export function evalGoldPageCaption(input: {
  pageLabel: string | null;
  pageNumber: number | null;
}): string {
  if (input.pageLabel) {
    return input.pageLabel;
  }
  if (input.pageNumber !== null) {
    return `PDF page ${String(input.pageNumber)}`;
  }
  return "Page unknown";
}

/**
 * Return why Approve is blocked, or null when allowed.
 *
 * Stale gold and empty gold cannot approve.
 *
 * @param input - Saved gold state, not unsaved picker drafts.
 * @returns Accessible disabled reason, or null.
 */
export function evalApproveBlockedReason(input: {
  goldStale: boolean;
  goldCount: number;
  unsavedGold: boolean;
}): string | null {
  if (input.unsavedGold) {
    return "Save gold before approval.";
  }
  if (input.goldStale) {
    return "Remap gold from current passages before approval. Stale gold cannot be approved.";
  }
  if (input.goldCount < 1) {
    return "Select 1–3 current gold passages before approval.";
  }
  return null;
}

/** Official web exam metric name. Never used for citation overlap. */
export const EXAM_RECALL_METRIC_NAME =
  "All required gold chunks in the production Hybrid top 10";

/** Maximum poll delay in milliseconds. */
export const EXAM_POLL_MAX_MS = 15_000;

/** Initial poll delay in milliseconds. */
export const EXAM_POLL_MIN_MS = 2_000;

/**
 * Return a short hash prefix for scoreboard display.
 *
 * @param value - Full digest, or null.
 * @returns First eight characters, or `unknown`.
 */
export function shortEvalHash(value: string | null | undefined): string {
  if (!value) {
    return "unknown";
  }
  return value.slice(0, 8);
}

/**
 * Build the official Recall@10 headline.
 *
 * @param input - Hit count, case count, and optional stored ratio.
 * @returns Visible metric sentence naming the production corpus.
 */
export function examRecallHeadline(input: {
  hitCount: number;
  caseCount: number;
  ratio: number | null;
}): string {
  const ratio =
    input.ratio !== null
      ? input.ratio
      : input.caseCount === 0
        ? 0
        : input.hitCount / input.caseCount;
  const pct = Math.round(ratio * 100);
  return `${EXAM_RECALL_METRIC_NAME}: ${String(input.hitCount)} of ${String(input.caseCount)} (${String(pct)}%)`;
}

/**
 * Return whether an exam status is terminal.
 *
 * @param status - Exam run status.
 * @returns True for succeeded, failed, or cancelled.
 */
export function isExamTerminal(status: string): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

/**
 * Return whether an exam should keep polling.
 *
 * @param status - Exam run status.
 * @returns True for queued or running.
 */
export function isExamActive(status: string): boolean {
  return status === "queued" || status === "running";
}

/**
 * Bounded exponential backoff for exam polling.
 *
 * @param updateCount - Successful poll count from the query.
 * @returns Delay in milliseconds, 2s doubling to 15s.
 */
export function examPollIntervalMs(updateCount: number): number {
  const exponent = Math.max(0, updateCount - 1);
  return Math.min(EXAM_POLL_MIN_MS * 2 ** exponent, EXAM_POLL_MAX_MS);
}
