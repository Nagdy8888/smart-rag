/**
 * Display helpers for `GET /ingestion/versions/{id}/status`.
 *
 * BM25 index/lag live on this payload, not on SSE chat events.
 */

import type { Bm25Diagnostics, GraphHandoffDiagnostics, IngestionJobSummary } from "./types";
import { formatRelativeTime } from "./relative-time";
import { isRealDetailValue } from "./run-details";

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
    hybrid_ready: "Search ready",
    graph_pending: "Graph pending",
    graph_ready: "Graph ready",
    graph_ineligible: "Graph ineligible",
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
    graph_pending: { label: "Graph pending", tone: "warning" },
    graph_ready: { label: "Graph ready", tone: "success" },
    graph_ineligible: { label: "Graph ineligible", tone: "neutral" },
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
      ? "Graph ready"
      : status === "graph_ineligible"
        ? "Graph ineligible"
        : "Graph pending";
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

/** One user-visible technical-details row. */
export type IngestionDetailRow = {
  /** Sentence-case label. */
  label: string;
  /** Already-safe display value. */
  value: string;
};

const JOB_KIND_LABELS: Readonly<Record<string, string>> = {
  scan_promote: "Scanning",
  website_crawl: "Website crawl",
  hybrid_index: "Search indexing",
  lightrag_index: "Graph indexing",
};

const JOB_STATUS_LABELS: Readonly<Record<string, string>> = {
  pending: "Waiting",
  processing: "In progress",
  completed: "Completed",
  failed: "Failed",
  dead_letter: "Needs retry",
  backoff: "Waiting to retry",
};

/**
 * Map a stored job kind onto a sentence-case label.
 *
 * @param kind - `ingestion_jobs.job_kind`.
 * @returns Known label, or spaced snake_case when unknown.
 */
export function ingestionJobKindLabel(kind: string): string {
  return JOB_KIND_LABELS[kind] ?? kind.replaceAll("_", " ");
}

/**
 * Map a stored job status onto a sentence-case label.
 *
 * @param status - `ingestion_jobs.status`.
 * @returns Known label, or spaced snake_case when unknown.
 */
export function ingestionJobStatusLabel(status: string): string {
  return JOB_STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

/**
 * Return whether a job is still interesting on the document page.
 *
 * Completed jobs stay off the list; retryable failures remain.
 *
 * @param status - Job status enum.
 * @returns False for completed.
 */
export function isOpenIngestionJob(status: string): boolean {
  return status !== "completed";
}

/**
 * Build BM25 rows that skip idle zeros and `none` indexes.
 *
 * @param bm25 - Nested diagnostics.
 * @returns Rows to render. Empty when there is nothing real to show.
 */
export function bm25DetailRows(bm25: Bm25Diagnostics): IngestionDetailRow[] {
  const rows: IngestionDetailRow[] = [];
  if (bm25.active_index_version !== null) {
    rows.push({
      label: "Search index",
      value: `Version ${String(bm25.active_index_version)}`,
    });
  }
  if (isRealDetailValue(bm25.verified_at)) {
    rows.push({
      label: "Search index verified",
      value: formatRelativeTime(bm25.verified_at),
    });
  }
  if (bm25.pending > 0) {
    rows.push({ label: "Search index waiting", value: String(bm25.pending) });
  }
  if (bm25.processing > 0) {
    rows.push({ label: "Search index running", value: String(bm25.processing) });
  }
  if (bm25.failed > 0) {
    rows.push({ label: "Search index failed", value: String(bm25.failed) });
  }
  if (bm25.dead_letter > 0) {
    rows.push({ label: "Search index needs retry", value: String(bm25.dead_letter) });
  }
  return rows;
}

/**
 * Build graph-handoff rows that skip all-zero idle counts.
 *
 * @param handoff - Nested diagnostics.
 * @returns Rows to render.
 */
export function graphHandoffDetailRows(
  handoff: GraphHandoffDiagnostics,
): IngestionDetailRow[] {
  const rows: IngestionDetailRow[] = [];
  if (handoff.completed > 0) {
    rows.push({ label: "Graph handoff completed", value: String(handoff.completed) });
  }
  if (handoff.pending > 0) {
    rows.push({ label: "Graph handoff waiting", value: String(handoff.pending) });
  }
  if (handoff.processing > 0) {
    rows.push({ label: "Graph handoff running", value: String(handoff.processing) });
  }
  if (handoff.failed > 0) {
    rows.push({ label: "Graph handoff failed", value: String(handoff.failed) });
  }
  if (handoff.dead_letter > 0) {
    rows.push({
      label: "Graph handoff needs retry",
      value: String(handoff.dead_letter),
    });
  }
  return rows;
}

/**
 * Return open jobs that still belong on the processing list.
 *
 * @param jobs - Recent job summaries.
 * @returns Non-completed jobs in API order.
 */
export function openIngestionJobs(
  jobs: readonly IngestionJobSummary[],
): IngestionJobSummary[] {
  return jobs.filter((job) => isOpenIngestionJob(job.status));
}
