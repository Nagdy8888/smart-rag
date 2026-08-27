/**
 * Unified ingestion status: compact pills on the list, timeline on detail.
 */

import type { ReactNode } from "react";
import { Button } from "../ui/button";
import { LimitationCallout } from "../ui/limitation-callout";
import { Sheet } from "../ui/sheet";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  bm25DetailRows,
  compactIngestionPills,
  graphHandoffDetailRows,
  ingestionJobKindLabel,
  ingestionJobStatusLabel,
  ingestionStatusTone,
  ingestionTimelineSteps,
  openIngestionJobs,
} from "../../lib/ingestion-status";
import { isRealDetailValue } from "../../lib/run-details";
import { limitationCopy } from "../../lib/limitations";
import type {
  DocumentIngestionStatusResponse,
  IngestionJobSummary,
} from "../../lib/types";
import styles from "./documents.module.css";

/** Bounded poll while a visible version is non-terminal. */
export const INGESTION_STATUS_POLL_MS = 5000;

/**
 * Return whether version status polling must stop.
 *
 * @param status - Server lifecycle enum.
 * @returns True for terminal public statuses, including deletion_pending.
 */
export function ingestionStatusIsTerminal(status: string): boolean {
  return (
    status === "hybrid_ready" ||
    status === "graph_ready" ||
    status === "graph_ineligible" ||
    status === "failed" ||
    status === "deletion_pending"
  );
}

export type IngestionStatusLayout = "pills" | "timeline";

export type IngestionStatusProps = {
  /** Envelope from `GET /ingestion/versions/{id}/status`. */
  payload: DocumentIngestionStatusResponse | undefined;
  /** Compact list pills or detail timeline. */
  layout: IngestionStatusLayout;
  /** Retry a job when `retry_allowed`. */
  onRetry?: (jobId: string) => void;
  /** True while a retry mutation is in flight. */
  retryPending?: boolean;
  /** Close the sheet. Required when `asSheet` is true. */
  onClose?: () => void;
  /** When true, wrap the timeline in the status sheet. */
  asSheet?: boolean;
};

/**
 * Render BM25, graph handoff, scan, OCR, jobs, and retry from real fields.
 *
 * @param props - Status payload, layout, and optional retry/close.
 * @returns Pills, timeline, or a sheet. No fetch of its own.
 */
export function IngestionStatus({
  payload,
  layout,
  onRetry,
  retryPending = false,
  onClose,
  asSheet = false,
}: IngestionStatusProps): ReactNode {
  if (payload === undefined) {
    if (layout === "pills") {
      return (
        <>
          <td>—</td>
          <td>—</td>
        </>
      );
    }
    return null;
  }
  const version = payload.version;
  if (layout === "pills") {
    const pills = compactIngestionPills(version.status);
    return (
      <>
        <td>
          {pills.search ? (
            <StatusPill status={pills.search.label} tone={pills.search.tone} />
          ) : (
            "—"
          )}
        </td>
        <td>
          {pills.graph ? (
            <StatusPill status={pills.graph.label} tone={pills.graph.tone} />
          ) : (
            "—"
          )}
        </td>
      </>
    );
  }
  const steps = ingestionTimelineSteps(version.status);
  const scanResult = version.scan?.result;
  const reviewCategory = version.review?.declared_category;
  const reviewPolicy = version.review?.attestation_policy_version;
  const bm25Rows = bm25DetailRows(version.bm25);
  const handoffRows = graphHandoffDetailRows(version.graph_handoff);
  const openJobs = openIngestionJobs(payload.recent_jobs ?? []);
  const chunkCount = version.chunk_count ?? 0;
  const ocrPages = version.ocr?.page_count ?? 0;
  const detailRows: { label: string; value: ReactNode }[] = [
    ...bm25Rows.map((row) => ({ label: row.label, value: row.value })),
    ...handoffRows.map((row) => ({ label: row.label, value: row.value })),
  ];
  if (chunkCount > 0) {
    detailRows.push({
      label: "Searchable chunks",
      value: String(chunkCount),
    });
  }
  if (ocrPages > 0) {
    detailRows.push({
      label: "Pages",
      value: String(ocrPages),
    });
  }
  if (isRealDetailValue(scanResult)) {
    detailRows.push({
      label: "Scan",
      value: <UserText value={scanResult} />,
    });
  }
  if (isRealDetailValue(reviewCategory)) {
    detailRows.push({
      label: "Attestation",
      value: (
        <>
          <UserText value={reviewCategory} />
          {isRealDetailValue(reviewPolicy) ? (
            <>
              {" "}
              <UserText value={reviewPolicy} />
            </>
          ) : null}
        </>
      ),
    });
  }
  const showDetails = detailRows.length > 0 || openJobs.length > 0;
  const body = (
    <div className={styles.formStack}>
      <ol className={styles.timeline}>
        {steps.map((step) => (
          <li key={step.id} className={styles.timelineStep} data-state={step.state}>
            <StatusPill
              status={step.label}
              tone={
                step.state === "current"
                  ? ingestionStatusTone(version.status)
                  : step.state === "done"
                    ? "success"
                    : "neutral"
              }
            />
          </li>
        ))}
      </ol>
      {version.status === "graph_pending" ? (
        <LimitationCallout tone="warning">
          {limitationCopy("graph_pending")}
        </LimitationCallout>
      ) : null}
      {showDetails ? (
        <details className={styles.details}>
          <summary>Technical details</summary>
          {detailRows.length > 0 ? (
            <dl className={styles.dl}>
              {detailRows.map((row) => (
                <div key={row.label} className={styles.detailRow}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {openJobs.length > 0 ? (
            <ul className={styles.jobList}>
              {openJobs.map((job: IngestionJobSummary) => (
                <li key={job.id}>
                  <UserText value={ingestionJobKindLabel(job.job_kind)} />
                  {" — "}
                  <UserText value={ingestionJobStatusLabel(job.status)} />
                  {version.retry_allowed && onRetry ? (
                    <Button
                      type="button"
                      variant="secondary"
                      pending={retryPending}
                      pendingLabel="Retrying…"
                      onClick={() => onRetry(job.id)}
                    >
                      Retry
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </details>
      ) : null}
    </div>
  );
  if (!asSheet) {
    return body;
  }
  if (onClose === undefined) {
    return body;
  }
  return (
    <Sheet title="Processing" onClose={onClose}>
      {body}
    </Sheet>
  );
}
