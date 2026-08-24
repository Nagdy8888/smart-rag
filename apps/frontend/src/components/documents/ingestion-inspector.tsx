/**
 * Sheet wrapper around the shared IngestionStatus timeline.
 */

import type { ReactNode } from "react";
import {
  IngestionStatus,
  type IngestionStatusProps,
} from "./ingestion-status";

export {
  INGESTION_STATUS_POLL_MS,
  ingestionStatusIsTerminal,
  IngestionStatus,
} from "./ingestion-status";

export type IngestionInspectorProps = Pick<
  IngestionStatusProps,
  "payload" | "onClose" | "onRetry" | "asSheet"
>;

/**
 * Render version diagnostics in a right sheet by default.
 *
 * @param props - Status payload, close, and retry.
 * @returns Shared IngestionStatus. No fetch of its own.
 */
export function IngestionInspector({
  payload,
  onClose,
  onRetry,
  asSheet = true,
}: IngestionInspectorProps): ReactNode {
  return (
    <IngestionStatus
      payload={payload}
      layout="timeline"
      asSheet={asSheet}
      onClose={onClose}
      onRetry={onRetry}
    />
  );
}
