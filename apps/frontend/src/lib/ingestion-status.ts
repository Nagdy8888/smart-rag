/**
 * Display helpers for `GET /ingestion/versions/{id}/status`.
 *
 * BM25 index/lag live on this payload, not on SSE chat events.
 */

import type { Bm25Diagnostics, GraphHandoffDiagnostics } from "./types";

/** Pill tone mapped from a lifecycle enum. */
export type IngestionStatusTone = "neutral" | "success" | "warning" | "danger";

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

/**
 * Map a lifecycle status to a pill tone. Graph Pending is warning, not danger.
 *
 * @param status - Server enum.
 * @returns Tone. Failed is danger; pending/lag is warning; ready is success.
 */
export function ingestionStatusTone(status: string): IngestionStatusTone {
  if (status === "failed") {
    return "danger";
  }
  if (
    status === "graph_pending" ||
    status === "deletion_pending" ||
    status === "uploading" ||
    status === "uploaded" ||
    status === "scanning" ||
    status === "parsing"
  ) {
    return "warning";
  }
  if (status === "hybrid_ready" || status === "graph_ready") {
    return "success";
  }
  return "neutral";
}

/**
 * Human label for a lifecycle enum. Does not invent statuses.
 *
 * @param status - Server value.
 * @returns Display label.
 */
export function ingestionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    uploading: "Uploading",
    uploaded: "Uploaded",
    scanning: "Scanning",
    parsing: "Parsing",
    hybrid_ready: "Hybrid Ready",
    graph_pending: "Graph Pending",
    graph_ready: "Graph Ready",
    graph_ineligible: "Graph Ineligible",
    deletion_pending: "Deletion pending",
    failed: "Failed",
  };
  return labels[status] ?? status;
}
