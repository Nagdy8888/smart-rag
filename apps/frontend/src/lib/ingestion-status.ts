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

/** Compact list-column labels derived from a real version lifecycle. */
export type CompactIngestionPills = {
  /** Search column. Null when the list has not loaded version status. */
  search: { label: string; tone: IngestionStatusTone } | null;
  /** Graph column. Null when graph has not started or status is unloaded. */
  graph: { label: string; tone: IngestionStatusTone } | null;
};

/**
 * Map a loaded version lifecycle onto Search/Graph list pills.
 *
 * Does not invent Hybrid Ready or Graph Ready from upload alone. Unknown
 * enums stay unlabeled.
 *
 * @param status - `version.status` from version status HTTP.
 * @returns Compact pills, or nulls when the enum is not a known lifecycle.
 */
export function compactIngestionPills(status: string): CompactIngestionPills {
  if (status === "failed") {
    return {
      search: { label: "Failed", tone: "danger" },
      graph: { label: "Failed", tone: "danger" },
    };
  }
  if (status === "deletion_pending") {
    return {
      search: { label: "Deletion pending", tone: "warning" },
      graph: { label: "Deletion pending", tone: "warning" },
    };
  }
  const searchByStatus: Record<string, CompactIngestionPills["search"]> = {
    uploading: { label: "Uploaded", tone: "warning" },
    uploaded: { label: "Uploaded", tone: "warning" },
    scanning: { label: "Scanning", tone: "warning" },
    parsing: { label: "Parsing", tone: "warning" },
    hybrid_ready: { label: "Search ready", tone: "success" },
    graph_pending: { label: "Search ready", tone: "success" },
    graph_ready: { label: "Search ready", tone: "success" },
    graph_ineligible: { label: "Search ready", tone: "success" },
  };
  const graphByStatus: Record<string, CompactIngestionPills["graph"]> = {
    graph_pending: { label: "Graph Pending", tone: "warning" },
    graph_ready: { label: "Graph Ready", tone: "success" },
    graph_ineligible: { label: "Graph Ineligible", tone: "neutral" },
  };
  return {
    search: searchByStatus[status] ?? null,
    graph: graphByStatus[status] ?? null,
  };
}

/** Ordered timeline rows for the detail IngestionStatus. */
export type IngestionTimelineStep = {
  /** Stable step id. */
  id: string;
  /** Visual contract label. */
  label: string;
  /** Whether this step is complete, current, or upcoming. */
  state: "done" | "current" | "upcoming";
};

const TIMELINE_ORDER = [
  "uploaded",
  "scanning",
  "parsing",
  "hybrid_ready",
  "graph",
] as const;

/**
 * Build a vertical timeline from a real lifecycle enum.
 *
 * Failed and deletion_pending replace the remaining unfinished steps.
 *
 * @param status - Server lifecycle.
 * @returns Ordered steps. Unknown enums yield a single current row.
 */
export function ingestionTimelineSteps(status: string): IngestionTimelineStep[] {
  if (status === "failed") {
    return [{ id: "failed", label: "Failed", state: "current" }];
  }
  if (status === "deletion_pending") {
    return [{ id: "deletion_pending", label: "Deletion pending", state: "current" }];
  }
  const cursor =
    status === "uploading" || status === "uploaded"
      ? "uploaded"
      : status === "scanning"
        ? "scanning"
        : status === "parsing"
          ? "parsing"
          : status === "hybrid_ready"
            ? "hybrid_ready"
            : status === "graph_pending" ||
                status === "graph_ready" ||
                status === "graph_ineligible"
              ? "graph"
              : null;
  if (cursor === null) {
    return [{ id: status, label: ingestionStatusLabel(status), state: "current" }];
  }
  const graphLabel =
    status === "graph_ready"
      ? "Graph Ready"
      : status === "graph_ineligible"
        ? "Graph Ineligible"
        : "Graph Pending";
  const labels: Record<(typeof TIMELINE_ORDER)[number], string> = {
    uploaded: "Uploaded",
    scanning: "Scanning",
    parsing: "Parsing",
    hybrid_ready: "Search ready",
    graph: graphLabel,
  };
  const currentIndex = TIMELINE_ORDER.indexOf(cursor);
  return TIMELINE_ORDER.map((id, index) => ({
    id,
    label: labels[id],
    state: index < currentIndex ? "done" : index === currentIndex ? "current" : "upcoming",
  }));
}
