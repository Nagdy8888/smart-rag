/**
 * Shared JSON parsers for run, feedback, and document rows.
 */

import type { DocumentResponse, FeedbackResponse, RunResponse } from "../types";

import { DOCUMENT_LIST_PAGE_SIZE } from "./documents-constants";

/**
 * Parse an owned run JSON body.
 *
 * @param body - FastAPI object.
 * @returns Run identifiers only. No transcript fields.
 */
export function parseRunResponse(body: Record<string, unknown>): RunResponse {
  return {
    run_id: String(body.run_id ?? ""),
    conversation_id: String(body.conversation_id ?? ""),
    creator_user_id: String(body.creator_user_id ?? ""),
    status: String(body.status ?? ""),
    reservation_id:
      body.reservation_id === null || body.reservation_id === undefined
        ? null
        : String(body.reservation_id),
    created_at:
      body.created_at === null || body.created_at === undefined
        ? null
        : String(body.created_at),
  };
}

/**
 * Parse a 201 feedback body.
 *
 * @param body - FastAPI object.
 * @returns Feedback id.
 */
export function parseFeedbackResponse(
  body: Record<string, unknown>,
): FeedbackResponse {
  return { feedback_id: String(body.feedback_id ?? "") };
}

/**
 * Map one FastAPI document object. Includes existing `created_at`.
 *
 * @param body - JSON object.
 * @returns Typed document row.
 */
export function parseDocumentResponse(body: Record<string, unknown>): DocumentResponse {
  return {
    document_id: String(body.document_id ?? ""),
    title: typeof body.title === "string" ? body.title : null,
    visibility: String(body.visibility ?? ""),
    current_version_id:
      typeof body.current_version_id === "string" ? body.current_version_id : null,
    visibility_generation: Number(body.visibility_generation ?? 0),
    created_at: typeof body.created_at === "string" ? body.created_at : null,
  };
}

/**
 * Build the next `created_at,id` cursor from the last row of a full page.
 *
 * @param page - Current page.
 * @param limit - Requested page size.
 * @returns Cursor string, or null when the page is short or `created_at` is missing.
 */
export function nextDocumentCursor(
  page: DocumentResponse[],
  limit: number = DOCUMENT_LIST_PAGE_SIZE,
): string | null {
  if (page.length < limit) {
    return null;
  }
  const last = page[page.length - 1];
  if (last === undefined || last.created_at === null || last.created_at === "") {
    return null;
  }
  return `${last.created_at},${last.document_id}`;
}
