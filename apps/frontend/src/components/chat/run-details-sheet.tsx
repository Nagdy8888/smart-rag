/**
 * Run details sheet. Closed by default. Diagnostics stay in the DOM for tests.
 */

"use client";

import { useEffect, useState } from "react";
import { INFERENCE_LINKS_UNAVAILABLE } from "../../lib/citation-drawer";
import type { ChatViewState } from "../../lib/chat-view";
import { formatRunTokenUsage, formatUsd } from "../../lib/format-usage";
import {
  cacheStatusLabel,
  correctionReasonLabel,
  routeIcon,
  routeLabel,
  routeSummary,
  runStatusLabel,
  runStatusSummary,
  runStatusTone,
} from "../../lib/run-details";
import { displayText } from "../../lib/safe-text";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { Sheet } from "../ui/sheet";
import { StatusPill } from "../ui/status-pill";
import { CodeText, UserText } from "../ui/user-text";
import transcriptStyles from "./chat-transcript.module.css";
import styles from "./run-details-sheet.module.css";

export type RunDetailsSheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
  /** Open handler. */
  onOpen: () => void;
  /** Current view. */
  chat: ChatViewState;
  /** Account usage USD string from `GET /usage/me`. */
  companyUsd: string;
  /** Caller usage label. Never company-wide spend. */
  usageLabel?: string;
};

const TOKEN_GROUPING = new Intl.NumberFormat("en-US");

/**
 * Copy a technical id and report clipboard success or failure.
 *
 * @param props - Exact id string already shown in monospace.
 * @returns Compact control. Missing clipboard support is a visible failure.
 */
function CopyIdButton({ value }: { value: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") {
      return;
    }
    const timer = window.setTimeout(() => {
      setState("idle");
    }, 2000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [state]);

  return (
    <Button
      type="button"
      variant="ghost"
      size="compact"
      aria-label={`Copy ${value}`}
      onClick={() => {
        void (async () => {
          if (navigator.clipboard?.writeText === undefined) {
            setState("failed");
            return;
          }
          try {
            await navigator.clipboard.writeText(value);
            setState("copied");
          } catch {
            setState("failed");
          }
        })();
      }}
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}
    </Button>
  );
}

/**
 * Render diagnostics. The panel stays mounted when the sheet is closed.
 *
 * @param props - Open state and chat diagnostics.
 * @returns Trigger, optional sheet, and always-mounted diagnostics panel.
 */
export function RunDetailsSheet({
  open,
  onClose,
  onOpen,
  chat,
  companyUsd,
}: RunDetailsSheetProps) {
  const diagnostics = chat.diagnostics;
  const statusValue = runStatusLabel(chat.terminal, chat.runId);
  const statusTone = runStatusTone(chat.terminal, chat.runId);
  const statusSummary =
    chat.runId === null
      ? null
      : runStatusSummary(chat.terminal, chat.progress.verificationCompleted);
  const effectiveRoute = diagnostics.effectiveRoute ?? chat.routeFamily;
  const searchMode = routeLabel(effectiveRoute);
  const searchSummary = routeSummary(effectiveRoute);
  const requested = routeLabel(diagnostics.requestedRoute);
  const showStartedAs =
    requested !== null &&
    searchMode !== null &&
    diagnostics.requestedRoute !== effectiveRoute;
  const changeReason = correctionReasonLabel(diagnostics.correctionReason);
  const cacheLabel = cacheStatusLabel(diagnostics.cacheStatus);
  const usageUsd = formatUsd(companyUsd);
  const runUsage = formatRunTokenUsage(
    diagnostics.promptTokens,
    diagnostics.completionTokens,
  );
  const hasRun = chat.runId !== null;
  const body = (
    <div className={styles.panel} data-testid="advanced-diagnostics">
      {hasRun ? (
        <p className={styles.lead}>How this answer was produced.</p>
      ) : (
        <EmptyState
          icon="spark"
          title="No answer yet"
          body="Send a question to see how that answer was produced, including search mode and token usage."
        />
      )}
      {statusValue ? (
        <section className={styles.card} data-tone={statusTone} aria-label="Status">
          <div className={styles.iconTile} aria-hidden="true">
            <Icon name="spark" />
          </div>
          <div>
            <p className={styles.kicker}>Status</p>
            <StatusPill status={statusValue} tone={statusTone} />
            {statusSummary ? <p className={styles.summary}>{statusSummary}</p> : null}
          </div>
        </section>
      ) : null}
      {searchMode ? (
        <section className={styles.card} data-tone="search" aria-label="Search mode">
          <div className={styles.iconTile} aria-hidden="true">
            <Icon name={routeIcon(effectiveRoute)} />
          </div>
          <div>
            <p className={styles.kicker}>Search mode</p>
            <h3 className={styles.title}>
              <UserText value={searchMode} />
            </h3>
            {searchSummary ? (
              <p className={styles.summary}>{searchSummary}</p>
            ) : null}
          </div>
        </section>
      ) : null}
      {showStartedAs || changeReason ? (
        <p className={styles.note}>
          {showStartedAs ? (
            <>
              Started as <UserText value={requested} />.{" "}
            </>
          ) : null}
          {changeReason ? <UserText value={changeReason} /> : null}
        </p>
      ) : null}
      {runUsage ? (
        <section aria-label="This run">
          <p className={styles.kicker}>This run</p>
          <div className={styles.metrics}>
            <div className={styles.metric}>
              <span className={styles.metricValue}>
                {TOKEN_GROUPING.format(diagnostics.promptTokens)}
              </span>
              <span className={styles.metricLabel}>Prompt tokens</span>
            </div>
            <div className={styles.metric}>
              <span className={styles.metricValue}>
                {TOKEN_GROUPING.format(diagnostics.completionTokens)}
              </span>
              <span className={styles.metricLabel}>Answer tokens</span>
            </div>
          </div>
          <p className={styles.srOnly}>{runUsage}</p>
        </section>
      ) : null}
      {usageUsd === "—" ? null : (
        <section className={styles.spend} aria-label="Your account">
          <p className={styles.kicker}>Your account</p>
          <p className={styles.spendValue}>{usageUsd}</p>
        </section>
      )}
      {diagnostics.toolKeys.length > 0 ? (
        <section aria-label="Tools used">
          <p className={styles.kicker}>Tools used</p>
          <div className={styles.chips}>
            {diagnostics.toolKeys.map((key) => (
              <StatusPill key={key} status={displayText(key)} />
            ))}
          </div>
        </section>
      ) : null}
      {cacheLabel ? (
        <p className={styles.summary}>
          <span className={styles.kicker}>Cache</span>
          <UserText value={cacheLabel} />
        </p>
      ) : null}
      {diagnostics.coverageScore === null ? null : (
        <p className={styles.summary}>
          <span className={styles.kicker}>Coverage</span>
          {String(diagnostics.coverageScore)}
        </p>
      )}
      {chat.runId ? (
        <section className={styles.ref} aria-label="Run ID">
          <p className={styles.kicker}>Run ID</p>
          <div className={styles.idRow}>
            <CodeText value={chat.runId} />
            <CopyIdButton value={chat.runId} />
          </div>
        </section>
      ) : null}
      {diagnostics.unknownEvents.length > 0 ? (
        <p className={styles.footnote}>
          Ignored stream events:{" "}
          {diagnostics.unknownEvents.map(displayText).join(", ")}
        </p>
      ) : null}
      <p className={styles.footnote}>{INFERENCE_LINKS_UNAVAILABLE}</p>
      <p className={styles.srOnly} data-testid="usage-strip">
        {runUsage ? `This run ${runUsage}. ` : null}
        Your account {usageUsd}.
      </p>
    </div>
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
        <Sheet title="Run details" onClose={onClose} panelClassName={styles.sheet}>
          {body}
        </Sheet>
      ) : (
        <div className={transcriptStyles.srOnly}>{body}</div>
      )}
    </>
  );
}
