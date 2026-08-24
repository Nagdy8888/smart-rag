/**
 * Version status inspector. Polling policy lives here so library and detail
 * share one terminal/interval contract.
 */

import type { ReactNode } from "react";
import { Button } from "../ui/button";
import { LimitationCallout } from "../ui/limitation-callout";
import { Sheet } from "../ui/sheet";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { DOCUMENT_DELETE_UNAVAILABLE } from "../../lib/citation-drawer";
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
  ingestionStatusLabel,
  ingestionStatusTone,
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

export type IngestionInspectorProps = {
  /** Envelope from `GET /ingestion/versions/{id}/status`. */
  payload: DocumentIngestionStatusResponse | undefined;
  /** Close the sheet and stop polling. */
  onClose: () => void;
  /** Retry a job when `retry_allowed`. */
  onRetry: (jobId: string) => void;
  /** When false, render inline without a sheet chrome. */
  asSheet?: boolean;
};

/**
 * Render BM25, graph handoff, scan, attestation, jobs, and delete-unavailable copy.
 *
 * @param props - Status payload and retry callback.
 * @returns Inspector body. No fetch of its own.
 */
export function IngestionInspector({
  payload,
  onClose,
  onRetry,
  asSheet = true,
}: IngestionInspectorProps): ReactNode {
  if (payload === undefined) {
    return null;
  }
  const version = payload.version;
  const body = (
    <div className={styles.formStack}>
      <StatusPill
        status={ingestionStatusLabel(version.status)}
        tone={ingestionStatusTone(version.status)}
      />
      <dl className={styles.dl}>
        <dt>BM25</dt>
        <dd>{formatBm25Summary(version.bm25)}</dd>
        <dt>Graph handoff</dt>
        <dd>{formatGraphHandoffSummary(version.graph_handoff)}</dd>
        <dt>Scan</dt>
        <dd>
          <UserText value={version.scan?.result ?? "none"} />
        </dd>
        <dt>Attestation</dt>
        <dd>
          <UserText value={version.review?.declared_category ?? "none"} />{" "}
          <UserText value={version.review?.attestation_policy_version ?? ""} />
        </dd>
      </dl>
      {version.status === "graph_pending" || !version.document_graph_eligible ? (
        <LimitationCallout tone="warning">
          {limitationCopy("graph_pending")} {graphNotReadyCopy(1)}
        </LimitationCallout>
      ) : null}
      {version.status === "deletion_pending" ? (
        <StatusPill status="deletion_pending" tone="warning" />
      ) : null}
      <p className={styles.muted}>{DOCUMENT_DELETE_UNAVAILABLE}</p>
      <ul className={styles.jobList}>
        {(payload.recent_jobs ?? []).map((job: IngestionJobSummary) => (
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
    </div>
  );
  if (!asSheet) {
    return body;
  }
  return (
    <Sheet title="Ingestion status" onClose={onClose}>
      {body}
    </Sheet>
  );
}
