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
  compactIngestionPills,
  formatBm25Summary,
  formatGraphHandoffSummary,
  ingestionStatusLabel,
  ingestionStatusTone,
  ingestionTimelineSteps,
} from "../../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../../lib/limitations";
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
      <StatusPill
        status={ingestionStatusLabel(version.status)}
        tone={ingestionStatusTone(version.status)}
      />
      {version.status === "graph_pending" || !version.document_graph_eligible ? (
        <LimitationCallout tone="warning">
          {limitationCopy("graph_pending")} {graphNotReadyCopy(1)}
        </LimitationCallout>
      ) : null}
      <details className={styles.details}>
        <summary>Technical details</summary>
        <dl className={styles.dl}>
          <dt>BM25</dt>
          <dd>{formatBm25Summary(version.bm25)}</dd>
          <dt>Graph handoff</dt>
          <dd>{formatGraphHandoffSummary(version.graph_handoff)}</dd>
          {version.scan ? (
            <>
              <dt>Scan</dt>
              <dd>
                <UserText value={version.scan.result ?? "none"} />
              </dd>
            </>
          ) : null}
          {version.review ? (
            <>
              <dt>Attestation</dt>
              <dd>
                <UserText value={version.review.declared_category ?? "none"} />{" "}
                <UserText value={version.review.attestation_policy_version ?? ""} />
              </dd>
            </>
          ) : null}
          {version.ocr ? (
            <>
              <dt>OCR</dt>
              <dd>
                pages={String(version.ocr.page_count)} ocr={String(version.ocr.ocr_pages)}
              </dd>
            </>
          ) : null}
        </dl>
        <ul className={styles.jobList}>
          {(payload.recent_jobs ?? []).map((job: IngestionJobSummary) => (
            <li key={job.id}>
              <UserText value={job.job_kind} /> — <UserText value={job.status} />
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
      </details>
    </div>
  );
  if (!asSheet) {
    return body;
  }
  if (onClose === undefined) {
    return body;
  }
  return (
    <Sheet title="Ingestion status" onClose={onClose}>
      {body}
    </Sheet>
  );
}
