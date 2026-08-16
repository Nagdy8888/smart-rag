/**
 * Display helpers for `GET /ingestion/versions/{id}/status`.
 *
 * BM25 index/lag live on this payload, not on SSE chat events.
 */

import type { Bm25Diagnostics, GraphHandoffDiagnostics } from "./types";

/**
 * Format BM25 index, lag, and queue counts as plain text.
 *
 * @param bm25 - Nested diagnostics from version status.
 * @returns One-line summary. Never treats missing index as ready.
 */
export function formatBm25Summary(bm25: Bm25Diagnostics): string {
  const index =
    bm25.active_index_version === null ? "none" : String(bm25.active_index_version);
  const schema = bm25.index_schema_version ?? "unset";
  const lag = bm25.lag_seconds === null ? "unknown" : `${String(bm25.lag_seconds)}s`;
  return [
    `index=${index}`,
    `schema=${schema}`,
    `lag=${lag}`,
    `pending=${String(bm25.pending)}`,
    `processing=${String(bm25.processing)}`,
    `failed=${String(bm25.failed)}`,
    `dead_letter=${String(bm25.dead_letter)}`,
    `retries=${String(bm25.retry_attempts)}`,
  ].join(" ");
}

/**
 * Format graph-handoff job counts. Upload reservation is never readiness.
 *
 * @param handoff - Nested graph_handoff object.
 * @returns One-line summary.
 */
export function formatGraphHandoffSummary(
  handoff: GraphHandoffDiagnostics,
): string {
  return [
    `pending=${String(handoff.pending)}`,
    `processing=${String(handoff.processing)}`,
    `completed=${String(handoff.completed)}`,
    `failed=${String(handoff.failed)}`,
    `dead_letter=${String(handoff.dead_letter)}`,
  ].join(" ");
}
