/**
 * Detail processing section. Delegates to the shared IngestionStatus timeline.
 */

import { IngestionStatus } from "./ingestion-status";
import type { DocumentIngestionStatusResponse } from "../../lib/types";
import styles from "./documents.module.css";

export type ProcessingTimelineProps = {
  /** Version status envelope. */
  payload: DocumentIngestionStatusResponse;
  /** Retry when `retry_allowed`. */
  onRetry: (jobId: string) => void;
};

/**
 * Render the ingestion timeline for a document version.
 *
 * @param props - Status payload and retry callback.
 * @returns Processing section wrapping IngestionStatus.
 */
export function ProcessingTimeline({ payload, onRetry }: ProcessingTimelineProps) {
  return (
    <section className={styles.section} aria-label="Processing">
      <h2>Processing</h2>
      <IngestionStatus payload={payload} layout="timeline" onRetry={onRetry} />
    </section>
  );
}
