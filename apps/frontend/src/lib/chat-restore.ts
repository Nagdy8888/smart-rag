/**
 * Pure helpers for transcript restore identities and citation selection.
 */

import { shouldShowCitations } from "./answer-origin";
import type { CitationResponse, ConversationMessage } from "./types";

/**
 * Return the newest persisted assistant run id.
 *
 * @param messages - Oldest-first transcript.
 * @returns Latest assistant `run_id`, or null.
 */
export function latestSettledRunId(
  messages: readonly ConversationMessage[],
): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const item = messages[index];
    if (
      item !== undefined &&
      item.role === "assistant" &&
      typeof item.run_id === "string" &&
      item.run_id !== ""
    ) {
      return item.run_id;
    }
  }
  return null;
}

/**
 * Choose the feedback target without using a reconnect pointer.
 *
 * Live in-flight runs (`terminal === null`) never receive feedback. After
 * reload, `activeRunId` is ignored unless that live answer already ended.
 *
 * @param activeRunId - Current SSE run, or null.
 * @param terminal - Live terminal, or null while streaming/idle.
 * @param viewingRunId - Selected historical turn.
 * @param settledRunId - Newest transcript assistant with a run id.
 * @returns Run to POST feedback to, or null when submit must stay disabled.
 */
export function feedbackTargetRunId(
  activeRunId: string | null,
  terminal: string | null,
  viewingRunId: string | null,
  settledRunId: string | null,
): string | null {
  if (activeRunId !== null && terminal !== null) {
    return activeRunId;
  }
  return viewingRunId ?? settledRunId;
}

/**
 * Return the citation list for the Sources sheet.
 *
 * Historical selection uses that run's list. Live chrome uses active-run
 * citations. The two identities stay distinct.
 *
 * @param viewingRunId - Selected historical run, or null for live.
 * @param activeRunId - In-flight or just-finished SSE run.
 * @param liveCitations - `GET /runs/{active}/citations`.
 * @param viewingCitations - `GET /runs/{viewing}/citations`.
 * @returns Rows for the sheet. Never a merged cross-run list.
 */
export function citationsForSources(
  viewingRunId: string | null,
  activeRunId: string | null,
  liveCitations: readonly CitationResponse[],
  viewingCitations: readonly CitationResponse[],
): readonly CitationResponse[] {
  if (viewingRunId === null || viewingRunId === activeRunId) {
    return liveCitations;
  }
  return viewingCitations;
}

/**
 * Clamp a transcript citation_count to the API contract.
 *
 * @param value - Raw JSON number.
 * @returns Integer 0..50.
 */
export function clampCitationCount(value: unknown): number {
  if (typeof value === "number" && Number.isInteger(value)) {
    return Math.min(50, Math.max(0, value));
  }
  if (typeof value === "string" && /^(0|[1-9]\d*)$/.test(value)) {
    return Math.min(50, Math.max(0, Number(value)));
  }
  return 0;
}

/**
 * Parse transcript source_kind. Mixed or unknown stays null.
 *
 * @param value - Raw JSON.
 * @returns Catalog kind, or null.
 */
export function parseTranscriptSourceKind(
  value: unknown,
): "company_document" | "web" | null {
  if (value === "company_document" || value === "web") {
    return value;
  }
  return null;
}

/**
 * Return whether header/mobile Sources chrome should render.
 *
 * Empty/legacy origin (`null`) keeps `Sources (0)`. General answers hide
 * the control. A historical viewing run keeps it open for that selection.
 *
 * @param origin - Live `answer_origin`, or null.
 * @param viewingRunId - Selected historical run, or null.
 * @returns True when the Sources button may appear.
 */
export function showSourcesControl(
  origin: string | null,
  viewingRunId: string | null,
): boolean {
  if (viewingRunId !== null) {
    return true;
  }
  return shouldShowCitations(origin);
}

/**
 * Choose the citation currently in the drawer.
 *
 * Detail wins when it matches the selection so excerpts load on demand.
 * The list row is the placeholder until that one detail returns.
 *
 * @param list - Active or viewing citation list.
 * @param selectedId - Selected citation id.
 * @param detail - Optional ACL-rechecked detail row.
 * @returns Selected citation, or null.
 */
export function selectedCitationRecord(
  list: readonly CitationResponse[],
  selectedId: string | null,
  detail: CitationResponse | null,
): CitationResponse | null {
  if (selectedId === null) {
    return null;
  }
  if (detail !== null && detail.citation_id === selectedId) {
    return detail;
  }
  return list.find((item) => item.citation_id === selectedId) ?? null;
}
