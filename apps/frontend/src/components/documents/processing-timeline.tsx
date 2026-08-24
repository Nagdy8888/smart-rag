/**
 * Processing section: lifecycle pill, BM25/handoff, jobs, retry.
 */

import { Button } from "../ui/button";
import { LimitationCallout } from "../ui/limitation-callout";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
  ingestionStatusLabel,
  ingestionStatusTone,
} from "../../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../../lib/limitations";
import type { DocumentIngestionStatusResponse } from "../../lib/types";
import styles from "./documents.module.css";

export type ProcessingTimelineProps = {
  /** Version status envelope. */
  payload: DocumentIngestionStatusResponse;
  /** Retry when `retry_allowed`. */
  onRetry: (jobId: string) => void;
};

/**
 * Render ingestion processing facts for a document version.
 *
 * @param props - Status payload and retry callback.
 * @returns Processing section body.
 */
export function ProcessingTimeline({ payload, onRetry }: ProcessingTimelineProps) {
  const version = payload.version;
  return (
    <section className={styles.section} aria-label="Processing">
      <h2>Processing</h2>
      <StatusPill
        status={ingestionStatusLabel(version.status)}
        tone={ingestionStatusTone(version.status)}
      />
      <dl className={styles.dl}>
        <dt>BM25</dt>
        <dd>{formatBm25Summary(version.bm25)}</dd>
        <dt>Graph handoff</dt>
        <dd>{formatGraphHandoffSummary(version.graph_handoff)}</dd>
      </dl>
      {version.status === "graph_pending" ? (
        <LimitationCallout tone="warning">
          {limitationCopy("graph_pending")} {graphNotReadyCopy(1)}
        </LimitationCallout>
      ) : null}
      {version.status === "deletion_pending" ? (
        <StatusPill status="deletion_pending" tone="warning" />
      ) : null}
      <ul className={styles.jobList}>
        {(payload.recent_jobs ?? []).map((job) => (
          <li key={job.id}>
            <UserText value={job.job_kind} /> — <UserText value={job.status} />
            {version.retry_allowed ? (
              <Button type="button" onClick={() => onRetry(job.id)}>
                Retry
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
