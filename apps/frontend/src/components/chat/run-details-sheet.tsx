/**
 * Run details sheet. Closed by default. Diagnostics stay in the DOM for tests.
 */

"use client";

import { INFERENCE_LINKS_UNAVAILABLE } from "../../lib/citation-drawer";
import type { ChatViewState } from "../../lib/chat-view";
import { formatRunTokenUsage, formatUsd } from "../../lib/format-usage";
import { displayText } from "../../lib/safe-text";
import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { UserText } from "../ui/user-text";
import styles from "./chat-transcript.module.css";

export type RunDetailsSheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
  /** Open handler. */
  onOpen: () => void;
  /** Current view. */
  chat: ChatViewState;
  /** Company usage USD string. */
  companyUsd: string;
  /** Caller usage label. Never company-wide spend. */
  usageLabel?: string;
};

/**
 * Render one diagnostic row when the value is real.
 *
 * @param label - Row title.
 * @param value - Display value. Dash and empty values are omitted.
 * @returns Fragment, or null.
 */
function DetailRow({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  if (value === null || value === undefined || value === "" || value === "—") {
    return null;
  }
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <UserText value={value} />
      </dd>
    </>
  );
}

/**
 * Render diagnostics. The definition list stays mounted when the sheet is closed.
 *
 * @param props - Open state and chat diagnostics.
 * @returns Trigger, optional sheet, and always-mounted diagnostics list.
 */
export function RunDetailsSheet({
  open,
  onClose,
  onOpen,
  chat,
  companyUsd,
}: RunDetailsSheetProps) {
  const diagnostics = chat.diagnostics;
  const terminalValue =
    chat.terminal !== null
      ? chat.terminal
      : chat.runId !== null
        ? "running"
        : null;
  const usageUsd = formatUsd(companyUsd);
  const runUsage =
    formatRunTokenUsage(diagnostics.promptTokens, diagnostics.completionTokens) ??
    "0 prompt · 0 completion";
  const body = (
    <>
      <dl data-testid="advanced-diagnostics">
        <DetailRow
          label="Requested route"
          value={diagnostics.requestedRoute ?? chat.routeFamily}
        />
        <DetailRow label="Effective route" value={diagnostics.effectiveRoute} />
        <DetailRow
          label="Corrected route"
          value={diagnostics.correctedRoute === null ? "none" : diagnostics.correctedRoute}
        />
        <DetailRow label="Correction reason" value={diagnostics.correctionReason} />
        <DetailRow label="Cache" value={diagnostics.cacheStatus} />
        <DetailRow
          label="Coverage"
          value={
            diagnostics.coverageScore === null
              ? null
              : String(diagnostics.coverageScore)
          }
        />
        <DetailRow
          label="Tools"
          value={diagnostics.toolKeys.map(displayText).join(", ") || "none"}
        />
        <dt>Heartbeats</dt>
        <dd>{String(diagnostics.heartbeatCount)}</dd>
        <DetailRow
          label="Unknown events"
          value={
            diagnostics.unknownEvents.length === 0
              ? "none (ignored)"
              : diagnostics.unknownEvents.join(", ")
          }
        />
        <DetailRow label="Stage" value={chat.stage} />
        <DetailRow label="Status" value={chat.status} />
        <DetailRow label="Terminal" value={terminalValue} />
      </dl>
      <p className={styles.muted}>{INFERENCE_LINKS_UNAVAILABLE}</p>
      <p className={styles.muted} data-testid="usage-strip">
        This run {runUsage}. Your account {usageUsd}.
      </p>
    </>
  );
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        data-action-id="ask.run_details"
        onClick={onOpen}
      >
        Run details
      </Button>
      {open ? (
        <Sheet title="Run details" onClose={onClose}>
          {body}
        </Sheet>
      ) : (
        <div className={styles.srOnly}>{body}</div>
      )}
    </>
  );
}
